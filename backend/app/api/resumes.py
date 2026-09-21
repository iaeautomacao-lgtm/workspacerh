import re
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.domain import Job,Candidate,Resume
from app.core.auth import require_rh
from app.models.domain import AuditLog
from app.models.workflow import Conversation
from app.models.exam import ExamAttempt
from app.services.uploads import store_resume, drop_file
router=APIRouter(prefix='/jobs/{job_id}/resumes',tags=['Resumes'])
@router.post('/upload')
async def upload(job_id:int,files:list[UploadFile]=File(...),db:Session=Depends(get_db)):
    job=db.get(Job,job_id)
    if not job: raise HTTPException(404,'Vaga não encontrada')
    if len(files)>30: raise HTTPException(422,'Envie até 30 currículos por vez.')
    results=[]
    for file in files:
        name,path,text=await store_resume(file)
        email=re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',text)
        phone=re.search(r'(?:\+?55\s*)?\(?\d{2}\)?[ .-]*9?\d{4}[ .-]*\d{4}',text)
        candidate=Candidate(company_id=job.company_id,name=name.rsplit('.',1)[0].replace('_',' '),email=email[0] if email else None,phone=phone[0] if phone else None)
        db.add(candidate);db.flush()
        resume=Resume(candidate_id=candidate.id,job_id=job.id,file_name=name,file_path=path,extracted_text=text);db.add(resume);db.flush()
        results.append({'id':resume.id,'name':candidate.name})
    db.commit();return {'resumes':results}

@router.delete('/{resume_id}')
def remove(job_id:int,resume_id:int,db:Session=Depends(get_db),account=Depends(require_rh)):
    """Exclui o currículo, o arquivo em disco e o candidato que ficar sem nenhum vínculo."""
    resume=db.get(Resume,resume_id)
    if not resume or resume.job_id!=job_id: raise HTTPException(404,'Currículo não encontrado')
    job=db.get(Job,job_id)
    candidate=resume.candidate
    name=candidate.name if candidate else resume.file_name
    drop_file(resume.file_path)
    db.delete(resume);db.flush()
    orphan=False
    if candidate:
        vinculos=(db.query(Resume).filter_by(candidate_id=candidate.id).count()
                  +db.query(Conversation).filter_by(candidate_id=candidate.id).count()
                  +db.query(ExamAttempt).filter_by(candidate_id=candidate.id).count())
        if not vinculos: db.delete(candidate);orphan=True
    db.add(AuditLog(company_id=job.company_id,user_id=account.id,action='resume_deleted',details=f'job={job_id} resume={resume_id} candidato={name[:120]}'))
    db.commit()
    return {'deleted':True,'candidate_removed':orphan}
