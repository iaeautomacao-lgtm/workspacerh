import hashlib
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.domain import Job, Resume, Screening, ScreeningResult
from app.models.workflow import JobPolicy
from app.models.exam import ExamAttempt
from app.services.matching_service import evaluate_matching
from app.services.llm_service import evaluate_with_ai, AIUnavailable

router=APIRouter(prefix='/jobs/{job_id}/screenings',tags=['Screenings'])
class RunInput(BaseModel):
    local_only: bool=False

def fingerprint(job,resumes):
    data=[job.description,[(r.category,r.title,r.weight) for r in job.requirements],[(r.id,r.extracted_text) for r in resumes]]
    return hashlib.sha256(json.dumps(data,ensure_ascii=False).encode()).hexdigest()

def attach_exams(job,rows,db):
    """Nota da prova em coluna própria: nunca é somada à aderência do currículo."""
    best={}
    for a in db.query(ExamAttempt).filter(ExamAttempt.job_id==job.id,ExamAttempt.candidate_id!=None).order_by(ExamAttempt.id).all():
        score=a.final_score if a.final_score is not None else a.objective_score
        current=best.get(a.candidate_id)
        if current is None or (score is not None and (current['exam_score'] is None or score>current['exam_score'])):
            best[a.candidate_id]={'exam_score':score,'exam_status':a.status,'exam_attempt_id':a.id}
    for row in rows: row.update(best.get(row['candidate_id']) or {'exam_score':None,'exam_status':None,'exam_attempt_id':None})

def summary(job,db):
    latest=db.query(Screening).filter_by(job_id=job.id,status='completed').order_by(Screening.id.desc()).first()
    resumes=db.query(Resume).filter_by(job_id=job.id).order_by(Resume.id).all()
    current=fingerprint(job,resumes)
    policy=db.get(JobPolicy,job.id)
    rows=[]
    if latest:
        for row in sorted(latest.results,key=lambda r:(-r.score,r.resume_id)):
            resume=row.resume
            if not resume: continue
            candidate=resume.candidate
            rows.append({'id':resume.id,'candidate_id':resume.candidate_id,'job_id':job.id,'name':candidate.name if candidate else resume.file_name,'candidate_name':candidate.name if candidate else resume.file_name,'phone':candidate.phone if candidate else None,'email':candidate.email if candidate else None,'score':row.score,'mandatory_matched':row.mandatory_matched,'experience':row.experience_summary,'status':row.status,'evidences':row.evidences})
    attach_exams(job,rows,db)
    stale=not latest or any((r['evidences'] or {}).get('fingerprint')!=current for r in rows) or len(rows)!=len(resumes)
    return {'results':rows,'total_candidates':len(resumes),'high_match_count':sum(r['score']>=80 for r in rows),'openings':policy.openings if policy else None,'stale':stale,'analyzed_at':latest.run_at if latest else None}

@router.get('')
def read(job_id:int,db:Session=Depends(get_db)):
    job=db.get(Job,job_id)
    if not job: raise HTTPException(404,'Vaga não encontrada')
    return summary(job,db)

@router.post('')
def run(job_id:int,body:RunInput,db:Session=Depends(get_db)):
    job=db.get(Job,job_id)
    if not job: raise HTTPException(404,'Vaga não encontrada')
    if not job.requirements: raise HTTPException(422,'Revise e cadastre os requisitos antes da análise.')
    resumes=db.query(Resume).filter_by(job_id=job.id).order_by(Resume.id).all()
    if not resumes: raise HTTPException(422,'Inclua currículos antes da análise.')
    signature=fingerprint(job,resumes)
    screening=Screening(job_id=job.id,status='completed');db.add(screening);db.flush()
    try:
        for res in resumes:
            name=res.candidate.name if res.candidate else 'Candidato'
            result=None if body.local_only else evaluate_with_ai(job.title,job.description,res.extracted_text,name,job.requirements)
            result=result or evaluate_matching(res.extracted_text,name,job.requirements)
            result['evidences']['fingerprint']=signature
            db.add(ScreeningResult(screening_id=screening.id,resume_id=res.id,score=result['score'],mandatory_matched=result['mandatory_matched'],experience_summary=result['experience'],status=result['status'],evidences=result['evidences']))
        db.commit()
    except AIUnavailable as exc:
        db.rollback();raise HTTPException(502,str(exc))
    return summary(job,db)
