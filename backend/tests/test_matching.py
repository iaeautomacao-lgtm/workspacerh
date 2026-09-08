from app.services.matching_service import evaluate_matching
from app.models.domain import JobRequirement

def test_evaluate_matching_high():
    reqs = [
        JobRequirement(category="mandatory", title="Ensino Médio"),
        JobRequirement(category="mandatory", title="Presencial"),
        JobRequirement(category="desirable", title="Atendimento"),
        JobRequirement(category="competency", title="Comunicação")
    ]
    resume_text = "Possuo Ensino Médio completo. Experiência de 2 anos com atendimento ao cliente presencial e boa comunicação."
    
    result = evaluate_matching(resume_text, "Ana Souza", reqs)
    
    assert result["score"] >= 80.0
    assert result["status"] == "Alta aderência"
    assert result["candidate_name"] == "Ana Souza"

def test_evaluate_matching_low():
    reqs = [
        JobRequirement(category="mandatory", title="Ensino Superior"),
        JobRequirement(category="mandatory", title="Inglês Fluente")
    ]
    resume_text = "Ensino fundamental incompleto. Sem experiência prévia."
    
    result = evaluate_matching(resume_text, "Carlos Melo", reqs)
    
    assert result["score"] < 80.0
    assert result["status"] == "Requer análise"
