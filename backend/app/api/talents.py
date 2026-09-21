import os
import secrets
import re
from pathlib import Path
from fastapi import APIRouter, Depends, Form, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import digest, require_rh
from app.models.domain import Job,Candidate,Resume
from app.models.workflow import Talent,InternalApplication,JobPolicy
from app.services.uploads import store_resume

public=APIRouter(prefix='/public',tags=['Internal careers'])
private=APIRouter(prefix='/talents',tags=['Talent management'],dependencies=[Depends(require_rh)])
@public.get('/jobs')
def jobs(db:Session=Depends(get_db)):
    rows=db.query(Job,JobPolicy).join(JobPolicy).filter(JobPolicy.internal==True,JobPolicy.published==True).all()
    return [{'id':j.id,'title':j.title,'description':j.description,'openings':p.openings,'location':p.location} for j,p in rows]

@public.post('/apply')
async def apply(name:str=Form(...,max_length=190),email:str=Form(...,max_length=190),phone:str=Form(...,max_length=30),employee_id:str=Form(...,max_length=100),department:str=Form(...,max_length=190),current_role:str=Form(...,max_length=190),interests:str=Form('',max_length=2000),consent:bool=Form(...),job_id:int|None=Form(None),update_token:str=Form('',max_length=100),file:UploadFile=File(...),db:Session=Depends(get_db)):
    if not consent: raise HTTPException(422,'É necessário autorizar o uso dos dados para recrutamento interno.')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(re.sub(r'\D','',phone)) not in (10,11,12,13): raise HTTPException(422,'Informe e-mail e telefone válidos.')
    if not all(v.strip() for v in [name,employee_id,department,current_role]): raise HTTPException(422,'Preencha os dados do colaborador.')
    job=None
    if job_id:
        job=db.get(Job,job_id);policy=db.get(JobPolicy,job_id)
        if not job or not policy or not policy.internal or not policy.published: raise HTTPException(404,'Vaga interna indisponível.')
    talent=db.query(Talent).filter_by(update_token_hash=digest(update_token)).first() if update_token else None
    if update_token and not talent: raise HTTPException(403,'Código de atualização inválido.')
    filename,path,text=await store_resume(file)
    token=secrets.token_urlsafe(32) if not talent else update_token
    if not talent:
        talent=Talent(update_token_hash=digest(token));db.add(talent)
    for key,value in dict(name=name.strip(),email=email.strip().lower(),phone=phone,employee_id=employee_id,department=department,current_role=current_role,interests=interests,file_name=filename,file_path=path,extracted_text=text).items(): setattr(talent,key,value)
    db.flush()
    if job:
        application=db.query(InternalApplication).filter_by(talent_id=talent.id,job_id=job.id).first()
        resume=db.get(Resume,application.resume_id) if application and application.resume_id else None
        if not resume:
            candidate=Candidate(company_id=job.company_id,name=name,email=email,phone=phone);db.add(candidate);db.flush()
            resume=Resume(candidate_id=candidate.id,job_id=job.id,file_name=filename,file_path=path,extracted_text=text);db.add(resume);db.flush()
        resume.file_name=filename;resume.file_path=path;resume.extracted_text=text
        resume.candidate.name=name;resume.candidate.phone=phone;resume.candidate.email=email
        if not application: db.add(InternalApplication(talent_id=talent.id,job_id=job.id,resume_id=resume.id))
    db.commit()
    return {'message':'Cadastro recebido pelo RH. Guarde seu código para atualizar seus dados e se candidatar a outras vagas.','update_token':token}

@private.get('')
def talents(db:Session=Depends(get_db)):
    return [{'id':t.id,'name':t.name,'email':t.email,'phone':t.phone,'employee_id':t.employee_id,'department':t.department,'current_role':t.current_role,'interests':t.interests,'created_at':t.created_at,'file_name':t.file_name,'applications':[{'job_id':a.job_id,'title':db.get(Job,a.job_id).title} for a in db.query(InternalApplication).filter_by(talent_id=t.id).all()]} for t in db.query(Talent).order_by(Talent.created_at.desc()).all()]

@private.get('/{talent_id}/resume')
def download(talent_id:int,db:Session=Depends(get_db)):
    t=db.get(Talent,talent_id)
    if not t or not Path(t.file_path).is_file(): raise HTTPException(404,'Arquivo não encontrado')
    return FileResponse(t.file_path,filename=t.file_name)
