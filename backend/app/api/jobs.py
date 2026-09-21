from typing import Literal, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import require_rh
from app.models.domain import Job, JobRequirement, Company
from app.models.workflow import JobPolicy
from app.services.job_parser import extract_text_from_url, structure_job_requirements, detect_openings
from app.services.llm_service import extract_job_ai, AIUnavailable
import os

router=APIRouter(prefix='/jobs', tags=['Jobs'])
class RequirementInput(BaseModel):
    category: Literal['mandatory','desirable','experience','competency']='mandatory'
    title: str=Field(min_length=2,max_length=500)
    weight: float=Field(default=1,gt=0,le=10)
class JobInput(BaseModel):
    title: str=Field(min_length=2,max_length=190)
    description: str=Field(min_length=10,max_length=40000)
    openings: Optional[int]=Field(default=None,ge=1,le=10000)
    internal: bool=False
    published: bool=False
    location: str=Field(default='A combinar',max_length=190)
    requirements: list[RequirementInput]=Field(default_factory=list,max_length=100)
    questions: list[str]=Field(default_factory=list,max_length=30)
    message_template: str=Field(default='Olá, {nome}! Aqui é o RH do Grupo DDM. Você tem interesse em conversar sobre a vaga {vaga}? Responda SIM para iniciar ou SAIR para encerrar.',max_length=4000)
    source_url: Optional[str]=Field(default=None,max_length=2000)
class SourceInput(BaseModel):
    source_type: Literal['url','text']='url'
    job_url: Optional[str]=Field(default=None,max_length=2000)
    description_text: Optional[str]=Field(default=None,max_length=40000)

def serialize(job, db):
    policy=db.get(JobPolicy,job.id)
    return {'id':job.id,'title':job.title,'description':job.description,'created_at':job.created_at,'requirements':[{'category':r.category,'title':r.title,'weight':r.weight} for r in job.requirements], **{k:getattr(policy,k,None) for k in ['openings','internal','published','location','questions','message_template','source_url']}}

@router.post('/extract')
def extract(body:SourceInput):
    try:
        text=extract_text_from_url(body.job_url or '') if body.source_type=='url' else body.description_text or ''
        if len(text)<20: raise ValueError('Inclua a descrição completa da vaga.')
        if os.getenv('OPENAI_API_KEY'):
            extracted=extract_job_ai(text); source='openai'
        else:
            extracted={'title':'','openings':detect_openings(text),'requirements':structure_job_requirements(text),'discarded':0}; source='local'
        return {**extracted,'description':text,'source':source,'source_url':body.job_url,'review_required':True}
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc) if isinstance(exc,ValueError) else 'Não foi possível ler a página. Cole a descrição da vaga.')

@router.get('')
def listing(db:Session=Depends(get_db)):
    return [serialize(j,db) for j in db.query(Job).order_by(Job.id.desc()).all()]

@router.post('')
def create(body:JobInput,db:Session=Depends(get_db)):
    company=db.query(Company).first()
    if not company:
        company=Company(name='Grupo DDM');db.add(company);db.flush()
    job=Job(company_id=company.id,title=body.title,description=body.description);db.add(job);db.flush()
    apply_job(job,body,db);db.commit()
    return serialize(job,db)

def apply_job(job,body,db):
    if any(not q.strip() or len(q)>500 for q in body.questions): raise HTTPException(422,'Perguntas devem ter entre 1 e 500 caracteres.')
    job.title=body.title;job.description=body.description
    job.requirements=[JobRequirement(category=r.category,title=r.title,weight=r.weight) for r in body.requirements]
    policy=db.get(JobPolicy,job.id)
    if not policy: policy=JobPolicy(job_id=job.id);db.add(policy)
    for key in ['openings','internal','published','location','questions','message_template','source_url']: setattr(policy,key,getattr(body,key))

@router.put('/{job_id}')
def update(job_id:int,body:JobInput,db:Session=Depends(get_db)):
    job=db.get(Job,job_id)
    if not job: raise HTTPException(404,'Vaga não encontrada')
    apply_job(job,body,db);db.commit();return serialize(job,db)

@router.delete('/{job_id}')
def remove(job_id:int,db:Session=Depends(get_db),account=Depends(require_rh)):
    """Exclui a vaga e o que só existe por causa dela. Registro de contato com candidato bloqueia."""
    from app.models.domain import AuditLog
    from app.models.workflow import Conversation,InternalApplication
    from app.models.exam import Exam,ExamAttempt
    from app.services.uploads import drop_file
    job=db.get(Job,job_id)
    if not job: raise HTTPException(404,'Vaga não encontrada')
    blocks=[]
    for count,label in ((db.query(Conversation).filter_by(job_id=job_id).count(),'conversa(s) de triagem'),
                        (db.query(ExamAttempt).filter_by(job_id=job_id).count(),'prova(s) aplicada(s)'),
                        (db.query(InternalApplication).filter_by(job_id=job_id).count(),'candidatura(s) interna(s)')):
        if count: blocks.append(f'{count} {label}')
    if blocks: raise HTTPException(409,'Esta vaga tem '+', '.join(blocks)+'. Esses registros documentam contato com candidatos e não são apagados junto.')
    from app.models.domain import Candidate,Resume
    removed=len(job.resumes)
    candidatos={r.candidate_id for r in job.resumes if r.candidate_id}
    for resume in job.resumes: drop_file(resume.file_path)
    db.query(Exam).filter_by(job_id=job_id).update({'job_id':None})
    policy=db.get(JobPolicy,job_id)
    if policy: db.delete(policy)
    db.delete(job);db.flush()
    # Candidato que só existia por causa desta vaga sai junto; quem teve contato permanece.
    orfaos=0
    for candidate_id in candidatos:
        vinculos=(db.query(Resume).filter_by(candidate_id=candidate_id).count()
                  +db.query(Conversation).filter_by(candidate_id=candidate_id).count()
                  +db.query(ExamAttempt).filter_by(candidate_id=candidate_id).count())
        if not vinculos:
            candidate=db.get(Candidate,candidate_id)
            if candidate: db.delete(candidate);orfaos+=1
    db.add(AuditLog(company_id=job.company_id,user_id=account.id,action='job_deleted',details=f'job={job_id} titulo={job.title[:120]} curriculos={removed} candidatos={orfaos}'))
    db.commit()
    return {'deleted':True,'resumes_removed':removed,'candidates_removed':orfaos}
