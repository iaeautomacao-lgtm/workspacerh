from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.domain import Job, JobRequirement, Company
from app.schemas.domain import JobCreate, JobResponse

router = APIRouter(prefix="/jobs", tags=["Jobs"])

@router.post("", response_model=JobResponse)
def create_job(job_in: JobCreate, db: Session = Depends(get_db)):
    company = db.query(Company).first()
    if not company:
        company = Company(name="Grupo DDM")
        db.add(company)
        db.commit()
        db.refresh(company)

    job = Job(company_id=company.id, title=job_in.title, description=job_in.description)
    db.add(job)
    db.commit()
    db.refresh(job)

    for req in job_in.requirements:
        j_req = JobRequirement(job_id=job.id, category=req.category, title=req.title, weight=req.weight)
        db.add(j_req)
    
    db.commit()
    return job

from app.schemas.domain import JobCreateFromSource
from app.services.job_parser import extract_text_from_url, structure_job_requirements

@router.post("/from-source", response_model=JobResponse)
def create_job_from_source(job_in: JobCreateFromSource, db: Session = Depends(get_db)):
    company = db.query(Company).first()
    if not company:
        company = Company(name="Grupo DDM")
        db.add(company)
        db.commit()
        db.refresh(company)

    if job_in.source_type == "url" and job_in.job_url:
        description_text = extract_text_from_url(job_in.job_url)
    else:
        description_text = job_in.description_text or f"Vaga: {job_in.title}"

    job = Job(company_id=company.id, title=job_in.title, description=description_text)
    db.add(job)
    db.commit()
    db.refresh(job)

    # Estrutura os critérios via IA / Parser
    reqs_structured = structure_job_requirements(description_text)
    for req in reqs_structured:
        db.add(JobRequirement(job_id=job.id, category=req["category"], title=req["title"], weight=req["weight"]))
    
    db.commit()
    return job


@router.get("", response_model=List[JobResponse])
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(Job).all()
    # Se não houver vagas cadastradas, insere vaga padrão para teste inicial
    if not jobs:
        company = db.query(Company).first()
        if not company:
            company = Company(name="Grupo DDM")
            db.add(company)
            db.commit()
            db.refresh(company)

        job_default = Job(
            company_id=company.id,
            title="Operador de Telemarketing (Presencial)",
            description="Atendimento ao cliente, resolução de dúvidas e registro de chamados."
        )
        db.add(job_default)
        db.commit()
        db.refresh(job_default)

        # Adiciona critérios de vaga
        db.add(JobRequirement(job_id=job_default.id, category="mandatory", title="Ensino Médio, Médio"))
        db.add(JobRequirement(job_id=job_default.id, category="mandatory", title="Presencial, Disponibilidade"))
        db.add(JobRequirement(job_id=job_default.id, category="desirable", title="Atendimento, Telemarketing"))
        db.add(JobRequirement(job_id=job_default.id, category="competency", title="Comunicação"))
        db.commit()
        jobs = [job_default]

    return jobs

@router.delete("/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Vaga não encontrada")
    
    db.delete(job)
    db.commit()
    return {"message": f"Vaga #{job_id} e seus currículos foram excluídos com sucesso"}
