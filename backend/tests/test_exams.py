from tests.test_workflow import PREFIX, create_job, upload

QUESTIONS = [
    {'kind': 'choice', 'statement': 'Qual fórmula procura um valor em outra tabela?', 'weight': 1, 'options': ['SOMASE', 'PROCV', 'CONT.SE'], 'answer_key': 1},
    {'kind': 'truefalse', 'statement': 'Férias podem ser divididas em até três períodos.', 'weight': 1, 'answer_key': True},
    {'kind': 'matching', 'statement': 'Associe o encargo à sigla.', 'weight': 2,
     'options': {'left': ['Fundo de garantia', 'Previdência'], 'right': ['INSS', 'FGTS']}, 'answer_key': [1, 0]},
    {'kind': 'essay', 'statement': 'Descreva como você conduz o fechamento mensal da folha.', 'weight': 2,
     'rubric': [{'name': 'Clareza', 'max': 5}, {'name': 'Domínio técnico', 'max': 5}]},
]

def build(c, job_id=None, questions=None):
    body = {'title': 'Prova de Departamento Pessoal', 'job_id': job_id, 'instructions': 'Leia com atenção.', 'duration_minutes': 30, 'questions': questions if questions is not None else QUESTIONS}
    response = c.post(PREFIX + '/exams', json=body)
    assert response.status_code == 200, response.text
    return response.json()

def opened(c, **kw):
    exam = build(c, **kw)
    assert c.post(f"{PREFIX}/exams/{exam['id']}/open", json={'open': True}).status_code == 200
    return exam

def sit(c, exam_id, **extra):
    body = {'name': 'Pessoa de Teste', 'email': 'teste@example.test', 'phone': '(21) 99999-1234', 'document': '123', 'consent': True}
    body.update(extra)
    response = c.post(f'{PREFIX}/public/exams/{exam_id}/start', json=body)
    assert response.status_code == 200, response.text
    return response.json()

def answers_for(started, essay='Confiro os eventos, valido o ponto e fecho a folha com a contabilidade.'):
    rows = []
    for question in started['questions']:
        if question['kind'] == 'choice': rows.append({'question_id': question['id'], 'response': 1})
        elif question['kind'] == 'truefalse': rows.append({'question_id': question['id'], 'response': True})
        elif question['kind'] == 'matching': rows.append({'question_id': question['id'], 'response': [1, 0]})
        else: rows.append({'question_id': question['id'], 'response': essay})
    return rows

def test_exam_routes_are_private(client):
    for route in ['/exams', '/attempts/1']:
        assert client.get(PREFIX + route).status_code == 401
    assert client.get(PREFIX + '/public/exams').status_code == 200

def test_answer_key_never_reaches_the_candidate(authenticated):
    c = authenticated
    exam = opened(c)
    listed = c.get(PREFIX + '/public/exams').json()
    assert [e['id'] for e in listed] == [exam['id']]
    assert 'questions' not in listed[0]
    started = sit(c, exam['id'])
    serialized = repr(started['questions'])
    assert 'answer_key' not in serialized and 'rubric' not in serialized
    assert all('answer_key' not in q and 'rubric' not in q for q in started['questions'])
    # O RH continua enxergando o gabarito.
    assert c.get(f"{PREFIX}/exams/{exam['id']}").json()['questions'][0]['answer_key'] == 1

def test_closed_exam_refuses_candidates(authenticated):
    c = authenticated
    exam = build(c)
    assert c.get(PREFIX + '/public/exams').json() == []
    assert c.post(f"{PREFIX}/public/exams/{exam['id']}/start", json={'name': 'Pessoa de Teste', 'email': 'a@b.test', 'phone': '21999991234', 'consent': True}).status_code == 404

def test_open_requires_questions_and_consent(authenticated):
    c = authenticated
    empty = build(c, questions=[])
    assert c.post(f"{PREFIX}/exams/{empty['id']}/open", json={'open': True}).status_code == 422
    exam = opened(c)
    assert c.post(f"{PREFIX}/public/exams/{exam['id']}/start", json={'name': 'Pessoa de Teste', 'email': 'a@b.test', 'phone': '21999991234', 'consent': False}).status_code == 422

def test_invalid_question_is_rejected(authenticated):
    c = authenticated
    for bad in [
        {'kind': 'choice', 'statement': 'Sem gabarito', 'options': ['a', 'b'], 'answer_key': None},
        {'kind': 'choice', 'statement': 'Gabarito fora da faixa', 'options': ['a', 'b'], 'answer_key': 5},
        {'kind': 'essay', 'statement': 'Sem rubrica', 'rubric': []},
        {'kind': 'matching', 'statement': 'Associação incompleta', 'options': {'left': ['a', 'b'], 'right': ['x', 'y']}, 'answer_key': [0]},
    ]:
        response = c.post(PREFIX + '/exams', json={'title': 'Prova inválida', 'questions': [bad]})
        assert response.status_code == 422, bad

def test_objective_is_graded_and_essay_waits_for_the_recruiter(authenticated):
    c = authenticated
    exam = opened(c)
    started = sit(c, exam['id'])
    headers = {'X-Exam-Token': started['token']}
    assert c.put(f"{PREFIX}/public/attempts/{started['attempt_id']}", json={'answers': answers_for(started)}, headers=headers).json()['saved'] is True
    result = c.post(f"{PREFIX}/public/attempts/{started['attempt_id']}/submit", json={'answers': answers_for(started)}, headers=headers)
    assert result.status_code == 200
    # O candidato recebe confirmação, nunca a nota.
    assert result.json()['received'] is True and 'score' not in result.json()
    attempt = c.get(f"{PREFIX}/attempts/{started['attempt_id']}").json()
    assert attempt['status'] == 'submitted'
    assert attempt['objective_score'] == 100.0
    assert attempt['final_score'] is None
    essay = [q for q in attempt['questions'] if q['kind'] == 'essay'][0]
    graded = c.post(f"{PREFIX}/attempts/{started['attempt_id']}/grade", json={'items': [{'question_id': essay['id'], 'scores': [5, 2.5], 'note': 'Boa estrutura.'}]})
    assert graded.status_code == 200, graded.text
    # objetivas 4 pontos cheios + discursiva 2 * 0.75 => 5.5 de 6
    assert graded.json()['final_score'] == 91.7
    assert graded.json()['status'] == 'graded'

def test_wrong_answers_score_zero_and_partial_matching_counts(authenticated):
    c = authenticated
    exam = opened(c)
    started = sit(c, exam['id'])
    headers = {'X-Exam-Token': started['token']}
    rows = []
    for question in started['questions']:
        if question['kind'] == 'choice': rows.append({'question_id': question['id'], 'response': 0})
        elif question['kind'] == 'truefalse': rows.append({'question_id': question['id'], 'response': False})
        elif question['kind'] == 'matching': rows.append({'question_id': question['id'], 'response': [1, 1]})
    c.post(f"{PREFIX}/public/attempts/{started['attempt_id']}/submit", json={'answers': rows}, headers=headers)
    attempt = c.get(f"{PREFIX}/attempts/{started['attempt_id']}").json()
    # Só metade da associação (peso 2) acertou: 1 de 4 pontos objetivos.
    assert attempt['objective_score'] == 25.0

def test_session_token_is_required(authenticated):
    c = authenticated
    exam = opened(c)
    started = sit(c, exam['id'])
    path = f"{PREFIX}/public/attempts/{started['attempt_id']}"
    assert c.put(path, json={'answers': []}, headers={'X-Exam-Token': 'outro-token'}).status_code == 403
    assert c.put(path, json={'answers': []}).status_code == 403
    assert c.post(path + '/submit', json={'answers': []}, headers={'X-Exam-Token': 'outro-token'}).status_code == 403

def test_time_limit_is_enforced_by_the_server(authenticated):
    from app.core.time import utcnow
    from datetime import timedelta
    from app.models.exam import ExamAttempt
    c = authenticated
    exam = opened(c)
    started = sit(c, exam['id'])
    headers = {'X-Exam-Token': started['token']}
    from app.core.database import get_db
    from app.main import app
    with next(app.dependency_overrides[get_db]()) as db:
        db.get(ExamAttempt, started['attempt_id']).expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert c.put(f"{PREFIX}/public/attempts/{started['attempt_id']}", json={'answers': []}, headers=headers).status_code == 409
    # A entrega ainda é aceita para não perder o que já foi respondido.
    assert c.post(f"{PREFIX}/public/attempts/{started['attempt_id']}/submit", json={'answers': []}, headers=headers).status_code == 200

def test_submitted_exam_cannot_be_reopened_or_edited(authenticated):
    c = authenticated
    exam = opened(c)
    started = sit(c, exam['id'])
    headers = {'X-Exam-Token': started['token']}
    c.post(f"{PREFIX}/public/attempts/{started['attempt_id']}/submit", json={'answers': answers_for(started)}, headers=headers)
    assert c.put(f"{PREFIX}/public/attempts/{started['attempt_id']}", json={'answers': []}, headers=headers).status_code == 409
    detail = c.get(f"{PREFIX}/exams/{exam['id']}").json()
    assert c.put(f"{PREFIX}/exams/{exam['id']}", json={'title': 'Outra', 'questions': QUESTIONS}).status_code == 409

def test_objective_questions_cannot_be_graded_by_hand(authenticated):
    c = authenticated
    exam = opened(c)
    started = sit(c, exam['id'])
    c.post(f"{PREFIX}/public/attempts/{started['attempt_id']}/submit", json={'answers': answers_for(started)}, headers={'X-Exam-Token': started['token']})
    choice = [q for q in started['questions'] if q['kind'] == 'choice'][0]
    assert c.post(f"{PREFIX}/attempts/{started['attempt_id']}/grade", json={'items': [{'question_id': choice['id'], 'scores': [1]}]}).status_code == 422

def test_ai_review_requires_configured_key(authenticated):
    c = authenticated
    exam = opened(c)
    started = sit(c, exam['id'])
    c.post(f"{PREFIX}/public/attempts/{started['attempt_id']}/submit", json={'answers': answers_for(started)}, headers={'X-Exam-Token': started['token']})
    assert c.post(f"{PREFIX}/attempts/{started['attempt_id']}/ai-review").status_code == 409

def test_score_reaches_the_ranking_without_touching_adherence(authenticated):
    c = authenticated
    job = create_job(c)
    row = upload(c, job['id'])
    exam = opened(c, job_id=job['id'])
    started = sit(c, exam['id'], email='teste@example.test')
    # O candidato do currículo é reaproveitado, não duplicado.
    assert c.get(f"{PREFIX}/attempts/{started['attempt_id']}").json()['candidate_id'] == row['candidate_id']
    c.post(f"{PREFIX}/public/attempts/{started['attempt_id']}/submit", json={'answers': answers_for(started)}, headers={'X-Exam-Token': started['token']})
    report = c.get(f"{PREFIX}/jobs/{job['id']}/screenings").json()
    candidate = [r for r in report['results'] if r['candidate_id'] == row['candidate_id']][0]
    assert candidate['exam_score'] == 100.0
    assert candidate['exam_status'] == 'submitted'
    # A aderência do currículo permanece intocada.
    assert candidate['score'] == row['score']

def test_duplicated_candidate_links_to_the_right_job(authenticated):
    c = authenticated
    # O mesmo currículo enviado em duas vagas cria dois cadastros com o mesmo e-mail.
    other = create_job(c)
    upload(c, other['id'])
    job = create_job(c)
    row = upload(c, job['id'])
    exam = opened(c, job_id=job['id'])
    started = sit(c, exam['id'], email='teste@example.test')
    linked = c.get(f"{PREFIX}/attempts/{started['attempt_id']}").json()['candidate_id']
    assert linked == row['candidate_id'], 'a prova precisa apontar para o candidato desta vaga, não para a cópia mais antiga'
    c.post(f"{PREFIX}/public/attempts/{started['attempt_id']}/submit", json={'answers': answers_for(started)}, headers={'X-Exam-Token': started['token']})
    report = c.get(f"{PREFIX}/jobs/{job['id']}/screenings").json()
    assert [r['exam_score'] for r in report['results'] if r['candidate_id'] == row['candidate_id']] == [100.0]
