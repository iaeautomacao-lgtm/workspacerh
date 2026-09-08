import re
from typing import List, Dict, Any
from app.models.domain import JobRequirement

# Dicionários de sinônimos e equivalência de mercado (Normalizador Inteligente Sem LLM)
SYNONYMS = {
    "superior": [
        "superior", "graduação", "graduacao", "bacharel", "licenciatura", 
        "tecnólogo", "tecnologo", "pós", "pos", "mba", "mestrado", "doutorado",
        "administração", "administracao", "contabilidade", "ciências contábeis",
        "recursos humanos", "rh", "gestão de rh", "direito", "faculdade", "universidade"
    ],
    "dp": [
        "dp", "departamento pessoal", "folha", "folha de pagamento", "esocial", 
        "e-social", "rescisão", "rescisao", "férias", "ferias", "ponto", 
        "admissão", "admissao", "benefícios", "beneficios", "clt", "encargos",
        "ponto eletrônico", "ponto eletronico", "trabalhista", "dirf", "rais"
    ],
    "presencial": [
        "presencial", "escritório", "escritorio", "presencialmente", "modelo presencial", 
        "unidade", "rio de janeiro", "rj", "clt", "disponibilidade", "integral"
    ],
    "excel": [
        "excel", "pacote office", "office", "sistemas", "planilhas", "word", "sistema", "legislação"
    ],
    "comunicação": [
        "comunicação", "comunicacao", "relacionamento", "atendimento", "analítico", "organização", "disciplina", "autonomia"
    ]
}

def check_keyword_match(req_title: str, text_lower: str) -> tuple[bool, str]:
    title_lower = req_title.lower()
    
    # 1. Checa correspondência direta
    keywords = [k.strip() for k in title_lower.replace("/", ",").replace("-", ",").split(",") if k.strip()]
    for kw in keywords:
        if len(kw) > 2 and kw in text_lower:
            return True, f"Encontrado termo '{kw}' no currículo."
            
    # 2. Checa via dicionário de sinônimos
    for category, syn_list in SYNONYMS.items():
        if any(term in title_lower for term in [category, "superior", "médio", "dp", "pessoal", "presencial", "excel", "comunicação", "organização"]):
            matched_syns = [syn for syn in syn_list if syn in text_lower]
            if matched_syns:
                return True, f"Encontrado termo '{matched_syns[0]}' no currículo (Equivalente)."
                
    return False, "Não identificado no texto do currículo."

def evaluate_matching(resume_text: str, candidate_name: str, requirements: List[JobRequirement]) -> Dict[str, Any]:
    """
    Motor de Matching Determinístico e Inteligente com Relatório Completo de Evidências
    Categorias:
    - 60% Obrigatórios
    - 20% Desejáveis
    - 10% Tempo / Relevância de Experiência
    - 10% Competências
    """
    text_lower = resume_text.lower()
    
    mandatory_reqs = [r for r in requirements if r.category == 'mandatory']
    desirable_reqs = [r for r in requirements if r.category == 'desirable']
    competency_reqs = [r for r in requirements if r.category == 'competency']
    
    # 1. Avaliação de Obrigatórios (60%)
    mandatory_met = 0
    mandatory_evidences = []
    for req in mandatory_reqs:
        is_match, evidence_text = check_keyword_match(req.title, text_lower)
        if is_match:
            mandatory_met += 1
            mandatory_evidences.append({"category": "OBRIGATÓRIO", "req": req.title, "status": "Atende", "detail": evidence_text})
        else:
            mandatory_evidences.append({"category": "OBRIGATÓRIO", "req": req.title, "status": "Não Atende", "detail": evidence_text})
            
    mandatory_ratio = (mandatory_met / len(mandatory_reqs)) if mandatory_reqs else 1.0
    score_mandatory = mandatory_ratio * 60.0

    # 2. Avaliação de Desejáveis (20%)
    desirable_met = 0
    desirable_evidences = []
    for req in desirable_reqs:
        is_match, evidence_text = check_keyword_match(req.title, text_lower)
        if is_match:
            desirable_met += 1
            desirable_evidences.append({"category": "DESEJÁVEL", "req": req.title, "status": "Atende", "detail": evidence_text})
        else:
            desirable_evidences.append({"category": "DESEJÁVEL", "req": req.title, "status": "Não Atende", "detail": evidence_text})
            
    desirable_ratio = (desirable_met / len(desirable_reqs)) if desirable_reqs else 1.0
    score_desirable = desirable_ratio * 20.0

    # 3. Avaliação de Experiência (10%)
    years_matches = re.findall(r'(\d+)\s*(?:ano|anos|meses|mês)', text_lower)
    max_years = max([int(y) for y in years_matches], default=0) if years_matches else 1
    
    if "senior" in text_lower or "sênior" in text_lower:
        max_years = max(max_years, 6)
    elif "pleno" in text_lower:
        max_years = max(max_years, 3)

    exp_summary = f"{max_years} ano(s)" if max_years > 0 else "1 ano"
    score_experience = min(max_years / 3.0, 1.0) * 10.0
    exp_evidence = {"category": "EXPERIÊNCIA", "req": "Tempo de Atuação no Currículo", "status": "Atende" if max_years >= 1 else "Não Atende", "detail": f"Identificado tempo acumulado de {exp_summary}."}

    # 4. Avaliação de Competências (10%)
    competency_met = 0
    competency_evidences = []
    for req in competency_reqs:
        is_match, evidence_text = check_keyword_match(req.title, text_lower)
        if is_match:
            competency_met += 1
            competency_evidences.append({"category": "COMPETÊNCIA", "req": req.title, "status": "Atende", "detail": evidence_text})
        else:
            competency_evidences.append({"category": "COMPETÊNCIA", "req": req.title, "status": "Não Atende", "detail": evidence_text})

    competency_ratio = (competency_met / len(competency_reqs)) if competency_reqs else 1.0
    score_competency = competency_ratio * 10.0

    # Score Final Determinístico
    final_score = round(score_mandatory + score_desirable + score_experience + score_competency, 1)
    status = "Alta aderência" if final_score >= 80.0 else "Requer análise"
    mandatory_str = f"{mandatory_met}/{len(mandatory_reqs)} atendidos" if mandatory_reqs else "100%"

    # Consolida TODAS as evidências para exibição completa na Ficha
    all_evidences = mandatory_evidences + desirable_evidences + [exp_evidence] + competency_evidences

    return {
        "candidate_name": candidate_name,
        "score": final_score,
        "mandatory_matched": mandatory_str,
        "experience": exp_summary,
        "status": status,
        "evidences": {
            "all": all_evidences,
            "mandatory": mandatory_evidences,
            "desirable": desirable_evidences,
            "experience": exp_evidence,
            "competency": competency_evidences
        }
    }
