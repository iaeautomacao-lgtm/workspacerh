import re
import unicodedata
from typing import List, Dict, Any
from app.models.domain import JobRequirement

WEIGHTS = {'mandatory': 60, 'desirable': 20, 'experience': 10, 'competency': 10}
LABELS = {'mandatory': 'OBRIGATÓRIO', 'desirable': 'DESEJÁVEL', 'experience': 'EXPERIÊNCIA', 'competency': 'COMPETÊNCIA'}
# Um requisito é uma frase inteira ("Experiência sólida em rotinas de Departamento Pessoal.").
# Exigir a frase literal no currículo nunca evidencia nada, por isso a evidência é medida
# pela cobertura dos termos de conteúdo do requisito. Continua sendo lexical: nenhuma
# equivalência semântica ou de domínio é inferida.
ATTENDS_COVERAGE = 0.65
PARTIAL_COVERAGE = 0.35
PARTIAL_CREDIT = 0.5

STOPWORDS = {
    'a', 'ao', 'aos', 'as', 'com', 'como', 'da', 'das', 'de', 'do', 'dos', 'e', 'em', 'entre', 'na', 'nas', 'no',
    'nos', 'o', 'os', 'ou', 'para', 'pela', 'pelo', 'por', 'que', 'se', 'sob', 'sobre', 'um', 'uma', 'ser', 'sua',
    'seu', 'suas', 'seus', 'nivel', 'area', 'areas', 'minimo', 'minima', 'desejavel', 'obrigatorio', 'preferencial',
}

def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))

def content_terms(req_title):
    title = normalize(req_title)
    title = re.sub(r'^(obrigatorio|desejavel|requisito|experiencia|competencia)\s*:\s*', '', title)
    words = re.findall(r'[a-z0-9]+', title)
    seen, terms = set(), []
    for word in words:
        if len(word) < 3 or word in STOPWORDS or word in seen: continue
        seen.add(word); terms.append(word)
    return terms

def term_pattern(term):
    # Tolera flexão (plural, gênero, conjugação) sem sair da própria palavra do requisito.
    if len(term) >= 8: stem = term[:-3]
    elif len(term) >= 6: stem = term[:-2]
    else: return r'(?<!\w)' + re.escape(term) + r'(?!\w)'
    return r'(?<!\w)' + re.escape(stem) + r'\w{0,4}(?!\w)'

def negated(text, start):
    prefix = text[max(0, start-35):start]
    return bool(re.search(r'(?<!\w)(sem|nao|nenhum|nunca)\s+(?:\w+\s+){0,3}$', prefix))

def check_keyword_match(req_title, resume_text):
    text = normalize(resume_text)
    terms = content_terms(req_title)
    if not terms:
        return 0.0, 'Requisito sem termos avaliáveis; confirmar com o RH.'
    total = sum(len(t) for t in terms)
    covered, best = 0, None
    for term in terms:
        match = re.search(term_pattern(term), text)
        if not match or negated(text, match.start()): continue
        covered += len(term)
        if best is None or len(term) > len(best[0]): best = (term, match)
    coverage = covered / total
    if not best:
        return coverage, 'Não evidenciado no currículo; confirmar com o candidato.'
    _, match = best
    snippet = resume_text[max(0, match.start()-45):match.end()+80].strip()
    return coverage, re.sub(r'\s+', ' ', snippet)

def status_for(coverage):
    if coverage >= ATTENDS_COVERAGE: return 'Atende'
    if coverage >= PARTIAL_COVERAGE: return 'Parcial'
    return 'Não evidenciado'

def credit(status):
    return 1.0 if status == 'Atende' else PARTIAL_CREDIT if status == 'Parcial' else 0.0

def score_evidence(requirements, evidence):
    active = {r.category for r in requirements if r.category in WEIGHTS}
    denominator = sum(WEIGHTS[c] for c in active)
    score = 0
    for category in active:
        rows = [(r, e) for r, e in zip(requirements, evidence) if r.category == category]
        total = sum(max(float(r.weight or 1), 0.1) for r, _ in rows)
        matched = sum(max(float(r.weight or 1), 0.1) * credit(e['status']) for r, e in rows)
        score += WEIGHTS[category] * matched / total
    return round(100 * score / denominator, 1) if denominator else 0

def evaluate_matching(resume_text: str, candidate_name: str, requirements: List[JobRequirement]) -> Dict[str, Any]:
    evidences = []
    for req in requirements:
        coverage, detail = check_keyword_match(req.title, resume_text)
        evidences.append({'category': LABELS.get(req.category, req.category), 'req': req.title, 'status': status_for(coverage), 'coverage': round(coverage, 2), 'detail': detail})
    mandatory = [e for e in evidences if e['category'] == 'OBRIGATÓRIO']
    score = score_evidence(requirements, evidences)
    durations = [(int(n) / 12 if unit.startswith('m') else int(n)) for n, unit in re.findall(r'\b(\d+)\s*(anos?|meses|mês)\s+(?:de\s+)?(?:experiência|atuação)', resume_text.lower())]
    experience = f'{max(durations):g} ano(s) declarados; validar períodos' if durations else 'Tempo não evidenciado'
    return {'candidate_name': candidate_name, 'score': score, 'mandatory_matched': f"{sum(e['status'] == 'Atende' for e in mandatory)}/{len(mandatory)} atendidos", 'experience': experience,
            'status': 'Alta aderência' if score >= 80 else 'Requer análise', 'evidences': {'all': evidences, 'mandatory': mandatory, 'source': 'local', 'summary': 'Análise lexical preliminar por cobertura de termos. Requer validação do RH; ausência de informação não significa falta de qualificação.'}}
