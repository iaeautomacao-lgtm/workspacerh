from app.core.time import utcnow
import re
import secrets
from datetime import timedelta
from typing import Literal, Any
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core.database import get_db
from app.core.auth import digest, require_rh
from app.models.domain import Job, Candidate, Resume, AuditLog
from app.models.exam import Exam, ExamQuestion, ExamAttempt, ExamAnswer, KINDS, OBJECTIVE
from app.services.exam_grading import objective_fraction, rubric_fraction, recompute
from app.services.llm_service import review_essay, AIUnavailable
from app.services import question_bank as bank

private = APIRouter(tags=['Exams'], dependencies=[Depends(require_rh)])
public = APIRouter(prefix='/public', tags=['Exam sitting'])

class Criterion(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    max: float = Field(gt=0, le=100)
class QuestionInput(BaseModel):
    kind: Literal['choice', 'truefalse', 'matching', 'essay']
    statement: str = Field(min_length=3, max_length=8000)
    weight: float = Field(default=1, gt=0, le=10)
    options: Any = None
    answer_key: Any = None
    rubric: list[Criterion] = Field(default_factory=list, max_length=12)
class ExamInput(BaseModel):
    title: str = Field(min_length=2, max_length=190)
    job_id: int | None = None
    instructions: str = Field(default='', max_length=8000)
    duration_minutes: int = Field(default=60, ge=5, le=600)
    level: Literal['operacional', 'junior', 'pleno', 'senior'] = 'junior'
    area: str = Field(default='', max_length=120)
    mode: Literal['online', 'presencial'] = 'online'
    access_code: str = Field(default='', max_length=40)
    questions: list[QuestionInput] = Field(default_factory=list, max_length=200)

def validate(question: QuestionInput):
    """O gabarito é conferido no servidor: uma prova inválida nunca chega ao candidato."""
    if question.kind == 'choice':
        options = question.options or []
        if not isinstance(options, list) or len(options) < 2 or len(options) > 10: raise HTTPException(422, f'Múltipla escolha exige de 2 a 10 alternativas: {question.statement[:60]}')
        if any(not str(o).strip() for o in options): raise HTTPException(422, 'Alternativa em branco.')
        if not isinstance(question.answer_key, int) or isinstance(question.answer_key, bool) or not 0 <= question.answer_key < len(options): raise HTTPException(422, f'Indique a alternativa correta: {question.statement[:60]}')
        return list(options), question.answer_key
    if question.kind == 'truefalse':
        if not isinstance(question.answer_key, bool): raise HTTPException(422, f'Indique verdadeiro ou falso: {question.statement[:60]}')
        return [], question.answer_key
    if question.kind == 'matching':
        options = question.options or {}
        left, right = options.get('left') or [], options.get('right') or []
        if not isinstance(left, list) or not isinstance(right, list) or not 2 <= len(left) <= 10 or not 2 <= len(right) <= 10: raise HTTPException(422, f'Associação exige de 2 a 10 itens de cada lado: {question.statement[:60]}')
        key = question.answer_key
        if not isinstance(key, list) or len(key) != len(left) or any(not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(right) for i in key): raise HTTPException(422, f'Informe a associação correta de cada item: {question.statement[:60]}')
        return {'left': list(left), 'right': list(right)}, list(key)
    if not question.rubric: raise HTTPException(422, f'Discursiva exige ao menos um critério de correção: {question.statement[:60]}')
    return [], None

def apply_questions(exam, rows, db):
    db.query(ExamQuestion).filter_by(exam_id=exam.id).delete()
    for position, row in enumerate(rows):
        options, key = validate(row)
        db.add(ExamQuestion(exam_id=exam.id, position=position, kind=row.kind, statement=row.statement, weight=row.weight, options=options, answer_key=key, rubric=[c.model_dump() for c in row.rubric]))

def questions_of(exam_id, db):
    return db.query(ExamQuestion).filter_by(exam_id=exam_id).order_by(ExamQuestion.position, ExamQuestion.id).all()

def public_question(q):
    """Serializador do candidato. Nunca inclui answer_key nem a rubrica de correção."""
    return {'id': q.id, 'kind': q.kind, 'statement': q.statement, 'weight': q.weight, 'options': q.options if q.kind in ('choice', 'matching') else []}

def full_question(q):
    return {**public_question(q), 'answer_key': q.answer_key, 'rubric': q.rubric}

def serialize(exam, db, counts=True):
    job = db.get(Job, exam.job_id) if exam.job_id else None
    data = {'id': exam.id, 'title': exam.title, 'job_id': exam.job_id, 'job': job.title if job else None, 'instructions': exam.instructions,
            'duration_minutes': exam.duration_minutes, 'open': exam.open, 'level': exam.level, 'area': exam.area, 'mode': exam.mode,
            'access_code': exam.access_code or '', 'created_at': exam.created_at}
    if counts:
        data['questions_count'] = db.query(ExamQuestion).filter_by(exam_id=exam.id).count()
        data['attempts_count'] = db.query(ExamAttempt).filter_by(exam_id=exam.id).count()
        data['pending_review'] = db.query(ExamAttempt).filter_by(exam_id=exam.id, status='submitted').count()
    return data

@private.get('/exams')
def listing(db: Session = Depends(get_db)):
    return [serialize(e, db) for e in db.query(Exam).order_by(Exam.id.desc()).all()]

@private.post('/exams')
def create(body: ExamInput, db: Session = Depends(get_db)):
    if body.job_id and not db.get(Job, body.job_id): raise HTTPException(404, 'Vaga não encontrada')
    exam = Exam(title=body.title, job_id=body.job_id, instructions=body.instructions, duration_minutes=body.duration_minutes,
                level=body.level, area=body.area, mode=body.mode, access_code=body.access_code.strip())
    db.add(exam); db.flush()
    apply_questions(exam, body.questions, db); db.commit()
    return serialize(exam, db)

@private.get('/exams/{exam_id}')
def detail(exam_id: int, db: Session = Depends(get_db)):
    exam = db.get(Exam, exam_id)
    if not exam: raise HTTPException(404, 'Prova não encontrada')
    return {**serialize(exam, db), 'questions': [full_question(q) for q in questions_of(exam_id, db)]}

@private.put('/exams/{exam_id}')
def update(exam_id: int, body: ExamInput, db: Session = Depends(get_db)):
    exam = db.get(Exam, exam_id)
    if not exam: raise HTTPException(404, 'Prova não encontrada')
    if db.query(ExamAttempt).filter_by(exam_id=exam_id).count(): raise HTTPException(409, 'Esta prova já foi aplicada. Duplique-a para alterar as questões sem invalidar as correções existentes.')
    exam.title = body.title; exam.job_id = body.job_id; exam.instructions = body.instructions; exam.duration_minutes = body.duration_minutes
    exam.level = body.level; exam.area = body.area; exam.mode = body.mode; exam.access_code = body.access_code.strip()
    apply_questions(exam, body.questions, db); db.commit()
    return serialize(exam, db)

class OpenInput(BaseModel):
    open: bool
@private.post('/exams/{exam_id}/open')
def toggle(exam_id: int, body: OpenInput, db: Session = Depends(get_db), account=Depends(require_rh)):
    exam = db.get(Exam, exam_id)
    if not exam: raise HTTPException(404, 'Prova não encontrada')
    if body.open and not questions_of(exam_id, db): raise HTTPException(422, 'Cadastre ao menos uma questão antes de abrir a aplicação.')
    exam.open = body.open
    db.add(AuditLog(company_id=0, user_id=account.id, action='exam_open' if body.open else 'exam_close', details=f'exam={exam_id}'))
    db.commit()
    return {'open': exam.open}

@private.get('/exam-library')
def library(db: Session = Depends(get_db)):
    """Matérias, níveis e modelos disponíveis, com a contagem de questões de cada um."""
    subjects = []
    for key, label in bank.SUBJECTS.items():
        por_nivel = {level: len(bank.pool(key, level)) for level in bank.ORDER}
        subjects.append({'key': key, 'label': label, 'total': sum(1 for r in bank.BANK if r['subject'] == key), 'by_level': por_nivel})
    templates = [{'key': k, 'title': v['title'], 'level': v['level'], 'duration_minutes': v['duration_minutes'],
                  'mix': [{'subject': s, 'label': bank.SUBJECTS[s], 'amount': n} for s, n in v['mix']],
                  'questions': len(bank.assemble(v['mix'], v['level']))} for k, v in bank.TEMPLATES.items()]
    return {'subjects': subjects, 'levels': [{'key': k, 'label': v} for k, v in bank.LEVELS.items()], 'templates': templates}

class BuildInput(BaseModel):
    title: str = Field(min_length=2, max_length=190)
    job_id: int | None = None
    level: Literal['operacional', 'junior', 'pleno', 'senior'] = 'junior'
    mode: Literal['online', 'presencial'] = 'online'
    area: str = Field(default='', max_length=120)
    duration_minutes: int | None = Field(default=None, ge=5, le=600)
    instructions: str = Field(default='', max_length=8000)
    access_code: str = Field(default='', max_length=40)
    template: str | None = None
    mix: list[dict] = Field(default_factory=list, max_length=20)

@private.post('/exams/build')
def build(body: BuildInput, db: Session = Depends(get_db), account=Depends(require_rh)):
    """Monta uma prova a partir da biblioteca: um modelo pronto ou uma seleção de matérias."""
    if body.job_id and not db.get(Job, body.job_id): raise HTTPException(404, 'Vaga não encontrada')
    if body.template:
        modelo = bank.TEMPLATES.get(body.template)
        if not modelo: raise HTTPException(404, 'Modelo de prova não encontrado')
        mix, level = modelo['mix'], modelo['level']
        duration = body.duration_minutes or modelo['duration_minutes']  # o modelo sugere; o RH pode sobrescrever
    else:
        mix = []
        for row in body.mix:
            subject, amount = row.get('subject'), int(row.get('amount') or 0)
            if subject not in bank.SUBJECTS: raise HTTPException(422, f'Matéria desconhecida: {subject}')
            if amount > 0: mix.append((subject, min(amount, 50)))
        if not mix: raise HTTPException(422, 'Escolha ao menos uma matéria com quantidade maior que zero.')
        level, duration = body.level, body.duration_minutes or 60
    rows = bank.assemble(mix, level)
    if not rows: raise HTTPException(422, 'A biblioteca não tem questões para essa combinação de matéria e nível.')
    exam = Exam(title=body.title, job_id=body.job_id, instructions=body.instructions, duration_minutes=duration,
                level=level, area=body.area, mode=body.mode, access_code=body.access_code.strip())
    db.add(exam); db.flush()
    for position, row in enumerate(rows):
        db.add(ExamQuestion(exam_id=exam.id, position=position, kind=row['kind'], statement=row['statement'],
                            weight=row['weight'], options=row['options'] or [], answer_key=row['answer_key'], rubric=row['rubric']))
    db.add(AuditLog(company_id=0, user_id=account.id, action='exam_built', details=f'exam={exam.id} questoes={len(rows)} nivel={level}'))
    db.commit()
    return serialize(exam, db)

def attempt_row(a, db):
    return {'id': a.id, 'exam_id': a.exam_id, 'name': a.name, 'email': a.email, 'phone': a.phone, 'document': a.document, 'candidate_id': a.candidate_id,
            'started_at': a.started_at, 'submitted_at': a.submitted_at, 'status': a.status, 'objective_score': a.objective_score, 'final_score': a.final_score}

@private.get('/exams/{exam_id}/attempts')
def attempts(exam_id: int, db: Session = Depends(get_db)):
    if not db.get(Exam, exam_id): raise HTTPException(404, 'Prova não encontrada')
    return [attempt_row(a, db) for a in db.query(ExamAttempt).filter_by(exam_id=exam_id).order_by(ExamAttempt.id.desc()).all()]

@private.get('/attempts/{attempt_id}')
def attempt(attempt_id: int, db: Session = Depends(get_db)):
    a = db.get(ExamAttempt, attempt_id)
    if not a: raise HTTPException(404, 'Prova do candidato não encontrada')
    answers = {x.question_id: x for x in db.query(ExamAnswer).filter_by(attempt_id=a.id).all()}
    rows = []
    for q in questions_of(a.exam_id, db):
        answer = answers.get(q.id)
        rows.append({**full_question(q), 'response': answer.response if answer else None, 'correct': answer.correct if answer else None,
                     'awarded': answer.awarded if answer else None, 'ai_suggestion': answer.ai_suggestion if answer else None, 'reviewer_note': answer.reviewer_note if answer else ''})
    return {**attempt_row(a, db), 'exam': serialize(db.get(Exam, a.exam_id), db, counts=False), 'questions': rows}

@private.post('/attempts/{attempt_id}/ai-review')
def ai_review(attempt_id: int, db: Session = Depends(get_db)):
    a = db.get(ExamAttempt, attempt_id)
    if not a: raise HTTPException(404, 'Prova do candidato não encontrada')
    if a.status == 'in_progress': raise HTTPException(409, 'A prova ainda está em andamento.')
    answers = {x.question_id: x for x in db.query(ExamAnswer).filter_by(attempt_id=a.id).all()}
    reviewed = 0
    try:
        for q in questions_of(a.exam_id, db):
            if q.kind != 'essay': continue
            answer = answers.get(q.id)
            if not answer or not str(answer.response or '').strip(): continue
            suggestion = review_essay(q.statement, q.rubric, str(answer.response))
            if suggestion is None: raise HTTPException(409, 'Configure a chave OpenAI no servidor para usar a sugestão de correção.')
            answer.ai_suggestion = suggestion; reviewed += 1
    except AIUnavailable as exc:
        db.rollback(); raise HTTPException(502, str(exc))
    db.commit()
    return {'reviewed': reviewed, 'message': 'Sugestões geradas. A nota final continua sendo do RH.'}

class GradeItem(BaseModel):
    question_id: int
    scores: list[float] = Field(default_factory=list, max_length=12)
    note: str = Field(default='', max_length=4000)
class GradeInput(BaseModel):
    items: list[GradeItem] = Field(min_length=1, max_length=200)

@private.post('/attempts/{attempt_id}/grade')
def grade(attempt_id: int, body: GradeInput, db: Session = Depends(get_db), account=Depends(require_rh)):
    a = db.get(ExamAttempt, attempt_id)
    if not a: raise HTTPException(404, 'Prova do candidato não encontrada')
    if a.status == 'in_progress': raise HTTPException(409, 'A prova ainda está em andamento.')
    questions = {q.id: q for q in questions_of(a.exam_id, db)}
    answers = {x.question_id: x for x in db.query(ExamAnswer).filter_by(attempt_id=a.id).all()}
    for item in body.items:
        question = questions.get(item.question_id)
        if not question: raise HTTPException(422, 'Questão não pertence a esta prova.')
        if question.kind in OBJECTIVE: raise HTTPException(422, 'Questões objetivas são corrigidas automaticamente.')
        answer = answers.get(question.id)
        if not answer:
            answer = ExamAnswer(attempt_id=a.id, question_id=question.id); db.add(answer); answers[question.id] = answer
        fraction = rubric_fraction(question, item.scores)
        if fraction is None: raise HTTPException(422, 'Informe a nota de cada critério da rubrica.')
        answer.awarded = round(question.weight * fraction, 4); answer.reviewer_note = item.note
    db.flush()
    recompute(a, list(questions.values()), list(answers.values()))
    db.add(AuditLog(company_id=0, user_id=account.id, action='exam_graded', details=f'attempt={a.id} final={a.final_score}'))
    db.commit()
    return attempt_row(a, db)

# ---------------------------------------------------------------- candidato

_starts: dict[str, list] = {}
def throttle(request: Request):
    """Limite simples por processo: a aplicação é presencial, em máquina do RH."""
    key = request.client.host if request.client else 'unknown'
    now = utcnow()
    recent = [t for t in _starts.get(key, []) if t > now - timedelta(minutes=10)]
    if len(recent) >= 20: raise HTTPException(429, 'Muitos inícios de prova deste computador. Aguarde alguns minutos.')
    _starts[key] = recent + [now]

@public.get('/exams')
def open_exams(db: Session = Depends(get_db)):
    rows = db.query(Exam).filter(Exam.open == True).order_by(Exam.id.desc()).all()
    return [{'id': e.id, 'title': e.title, 'job': (db.get(Job, e.job_id).title if e.job_id and db.get(Job, e.job_id) else None),
             'duration_minutes': e.duration_minutes, 'instructions': e.instructions, 'mode': e.mode,
             'requires_code': bool((e.access_code or '').strip())} for e in rows]

class StartInput(BaseModel):
    name: str = Field(min_length=3, max_length=190)
    email: str = Field(max_length=190)
    phone: str = Field(max_length=30)
    document: str = Field(default='', max_length=40)
    consent: bool
    access_code: str = Field(default='', max_length=40)

def link_candidate(exam, body, db):
    """Reaproveita o candidato já existente na vaga em vez de duplicar o cadastro."""
    if not exam.job_id: return None
    job = db.get(Job, exam.job_id)
    if not job: return None
    email = body.email.strip().lower()
    phone = re.sub(r'\D', '', body.phone or '')
    filters = [Candidate.email == email]
    if phone: filters.append(Candidate.phone.like(f'%{phone[-8:]}'))
    match = or_(*filters)
    # O mesmo candidato pode estar duplicado na empresa: vale quem tem currículo nesta vaga.
    found = db.query(Candidate).join(Resume, Resume.candidate_id == Candidate.id).filter(Resume.job_id == job.id).filter(match).first()
    if not found:
        found = db.query(Candidate).filter(Candidate.company_id == job.company_id).filter(match).first()
    if found: return found
    candidate = Candidate(company_id=job.company_id, name=body.name.strip(), email=email, phone=body.phone)
    db.add(candidate); db.flush()
    return candidate

@public.post('/exams/{exam_id}/start')
def start(exam_id: int, body: StartInput, request: Request, db: Session = Depends(get_db)):
    throttle(request)
    if not body.consent: raise HTTPException(422, 'É necessário autorizar o uso dos dados para este processo seletivo.')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', body.email.strip()): raise HTTPException(422, 'Informe um e-mail válido.')
    if len(re.sub(r'\D', '', body.phone or '')) not in (10, 11, 12, 13): raise HTTPException(422, 'Informe um telefone válido com DDD.')
    exam = db.get(Exam, exam_id)
    if not exam or not exam.open: raise HTTPException(404, 'Prova indisponível. Procure o RH.')
    esperado = (exam.access_code or '').strip()
    if esperado and not secrets.compare_digest(esperado, body.access_code.strip()):
        raise HTTPException(403, 'Código de acesso inválido. Confira o código enviado pelo RH.')
    questions = questions_of(exam_id, db)
    if not questions: raise HTTPException(409, 'Prova sem questões. Procure o RH.')
    candidate = link_candidate(exam, body, db)
    token = secrets.token_urlsafe(32)
    now = utcnow()
    attempt = ExamAttempt(exam_id=exam.id, job_id=exam.job_id, candidate_id=candidate.id if candidate else None, token_hash=digest(token),
                          name=body.name.strip(), email=body.email.strip().lower(), phone=body.phone, document=body.document.strip(),
                          started_at=now, expires_at=now + timedelta(minutes=exam.duration_minutes))
    db.add(attempt); db.commit()
    return {'attempt_id': attempt.id, 'token': token, 'expires_at': attempt.expires_at.isoformat() + 'Z', 'duration_minutes': exam.duration_minutes,
            'title': exam.title, 'instructions': exam.instructions, 'questions': [public_question(q) for q in questions]}

def sitting(attempt_id, token, db):
    attempt = db.get(ExamAttempt, attempt_id)
    if not attempt or not secrets.compare_digest(attempt.token_hash, digest(token or '')): raise HTTPException(403, 'Sessão de prova inválida.')
    return attempt

class AnswerInput(BaseModel):
    question_id: int
    response: Any = None
class SaveInput(BaseModel):
    answers: list[AnswerInput] = Field(default_factory=list, max_length=200)

def store(attempt, rows, db):
    questions = {q.id: q for q in questions_of(attempt.exam_id, db)}
    existing = {x.question_id: x for x in db.query(ExamAnswer).filter_by(attempt_id=attempt.id).all()}
    for row in rows:
        question = questions.get(row.question_id)
        if not question: continue
        response = row.response
        if question.kind == 'essay':
            response = str(response or '')[:20000]
        elif question.kind == 'choice' and not (isinstance(response, int) and not isinstance(response, bool)): response = None
        elif question.kind == 'truefalse' and not isinstance(response, bool): response = None
        elif question.kind == 'matching' and not isinstance(response, list): response = None
        answer = existing.get(question.id)
        if not answer:
            answer = ExamAnswer(attempt_id=attempt.id, question_id=question.id); db.add(answer); existing[question.id] = answer
        answer.response = response
    return questions, existing

@public.put('/attempts/{attempt_id}')
def save(attempt_id: int, body: SaveInput, x_exam_token: str = Header(default=''), db: Session = Depends(get_db)):
    attempt = sitting(attempt_id, x_exam_token, db)
    if attempt.status != 'in_progress': raise HTTPException(409, 'Esta prova já foi entregue.')
    if utcnow() > attempt.expires_at: raise HTTPException(409, 'O tempo da prova terminou. Clique em entregar.')
    store(attempt, body.answers, db); db.commit()
    return {'saved': True, 'seconds_left': max(0, int((attempt.expires_at - utcnow()).total_seconds()))}

@public.post('/attempts/{attempt_id}/submit')
def submit(attempt_id: int, body: SaveInput, x_exam_token: str = Header(default=''), db: Session = Depends(get_db)):
    attempt = sitting(attempt_id, x_exam_token, db)
    if attempt.status != 'in_progress': return {'received': True}
    questions, answers = store(attempt, body.answers, db)
    for question in questions.values():
        answer = answers.get(question.id)
        if question.kind not in OBJECTIVE: continue
        if not answer:
            answer = ExamAnswer(attempt_id=attempt.id, question_id=question.id); db.add(answer); answers[question.id] = answer
        fraction = objective_fraction(question, answer.response)
        answer.correct = fraction >= 1.0
        answer.awarded = round(question.weight * fraction, 4)
    attempt.status = 'submitted'; attempt.submitted_at = utcnow()
    db.flush()
    recompute(attempt, list(questions.values()), list(answers.values()))
    db.commit()
    # O candidato nunca recebe a nota: o retorno é do RH.
    return {'received': True, 'message': 'Prova entregue. O RH dará o retorno do processo seletivo.'}
