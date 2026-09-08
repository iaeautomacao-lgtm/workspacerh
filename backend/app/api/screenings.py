from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.domain import Job, Resume, Screening, ScreeningResult
from app.schemas.domain import ScreeningSummaryResponse, ScreeningResultResponse
from app.services.matching_service import evaluate_matching
from app.services.llm_service import evaluate_with_ai

router = APIRouter(prefix="/jobs/{job_id}/screenings", tags=["Screenings"])

@router.get("", response_model=ScreeningSummaryResponse)
def get_or_run_screening(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Vaga não encontrada")

    resumes = db.query(Resume).filter(Resume.job_id == job_id).all()
    requirements = job.requirements

    results_list = []
    high_match_count = 0

    for res in resumes:
        candidate_name = res.candidate.name if res.candidate else "Candidato"
        
        # 1. Tenta avaliar com IA (Gemini / OpenAI / Groq)
        match_result = evaluate_with_ai(job.title, job.description, res.extracted_text, candidate_name)
        
        # 2. Se não houver chave de IA, usa o motor local
        if not match_result:
            match_result = evaluate_matching(res.extracted_text, candidate_name, requirements)

        if match_result["score"] >= 80.0:
            high_match_count += 1

        results_list.append(ScreeningResultResponse(
            id=res.id,
            candidate_name=candidate_name,
            name=candidate_name,
            score=match_result["score"],
            mandatory_matched=match_result["mandatory_matched"],
            experience=match_result["experience"],
            status=match_result["status"],
            evidences=match_result["evidences"]
        ))

    # Ordena por maior pontuação (ranking explicável)
    results_list.sort(key=lambda x: x.score, reverse=True)

    return ScreeningSummaryResponse(
        total_candidates=len(resumes),
        high_match_count=high_match_count,
        results=results_list
    )
