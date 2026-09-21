"""Correção das provas. A parte objetiva é automática; a discursiva é sempre do RH.

Nenhuma nota é exibida ao candidato: a prova apenas confirma o recebimento.
"""
from app.models.exam import OBJECTIVE

def objective_fraction(question, response):
    """Fração de acerto (0..1) de uma questão objetiva. None quando não respondida."""
    key = question.answer_key
    if response is None or key is None: return 0.0
    if question.kind == 'choice':
        return 1.0 if isinstance(response, int) and response == key else 0.0
    if question.kind == 'truefalse':
        return 1.0 if isinstance(response, bool) and response == bool(key) else 0.0
    if question.kind == 'matching':
        pairs = list(key or [])
        if not pairs or not isinstance(response, list): return 0.0
        given = (list(response) + [None] * len(pairs))[:len(pairs)]
        return sum(1 for expected, got in zip(pairs, given) if expected == got) / len(pairs)
    return 0.0

def rubric_fraction(question, scores):
    """Fração de acerto de uma discursiva a partir das notas por critério do RH."""
    criteria = list(question.rubric or [])
    if not criteria or not isinstance(scores, list): return None
    total = sum(float(c.get('max') or 0) for c in criteria)
    if total <= 0: return None
    given = sum(min(max(float(s or 0), 0), float(c.get('max') or 0)) for c, s in zip(criteria, scores + [0] * len(criteria)))
    return given / total

def percentage(rows):
    """rows: iterável de (weight, fraction). Ignora questões ainda sem correção."""
    graded = [(w, f) for w, f in rows if f is not None]
    total = sum(max(w, 0.1) for w, _ in graded)
    if total <= 0: return None
    return round(100 * sum(max(w, 0.1) * f for w, f in graded) / total, 1)

def recompute(attempt, questions, answers):
    """Atualiza objective_score, final_score e status a partir das respostas gravadas."""
    by_question = {a.question_id: a for a in answers}
    objective, every = [], []
    pending = False
    for question in questions:
        answer = by_question.get(question.id)
        awarded = answer.awarded if answer else None
        fraction = None if awarded is None else awarded / max(question.weight, 0.1)
        if question.kind in OBJECTIVE: objective.append((question.weight, fraction))
        elif fraction is None: pending = True
        every.append((question.weight, fraction))
    attempt.objective_score = percentage(objective)
    attempt.final_score = None if pending else percentage(every)
    if attempt.status != 'in_progress':
        attempt.status = 'submitted' if pending else 'graded'
    return attempt
