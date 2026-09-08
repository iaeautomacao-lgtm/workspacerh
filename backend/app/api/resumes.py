import os
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.core.config import settings
from app.models.domain import Job, Candidate, Resume, Company
from app.services.resume_parser import extract_text_from_file

router = APIRouter(prefix="/jobs/{job_id}/resumes", tags=["Resumes"])

@router.post("/upload")
async def upload_resumes(job_id: int, files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Vaga não encontrada")

    processed_resumes = []
    
    for file in files:
        # Salva o arquivo fisicamente
        file_path = os.path.join(settings.UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Realiza a extração textual real (PyMuPDF / python-docx)
        extracted_text = extract_text_from_file(file_path)
        
        # Tenta derivar o nome do candidato a partir do nome do arquivo
        base_name = os.path.splitext(file.filename)[0].replace("_", " ").replace("-", " ").title()
        
        # Registra o candidato e o currículo
        candidate = Candidate(company_id=job.company_id, name=base_name)
        db.add(candidate)
        db.commit()
        db.refresh(candidate)

        resume = Resume(
            candidate_id=candidate.id,
            job_id=job.id,
            file_name=file.filename,
            file_path=file_path,
            extracted_text=extracted_text
        )
        db.add(resume)
        db.commit()
        db.refresh(resume)
        
        processed_resumes.append({"id": resume.id, "file_name": file.filename, "candidate_name": base_name})

    return {"message": f"{len(processed_resumes)} currículo(s) processado(s) com sucesso", "resumes": processed_resumes}

@router.delete("/resumes/{resume_id}")
def delete_resume(resume_id: int, db: Session = Depends(get_db)):
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Currículo não encontrado")

    # Remove o arquivo físico se existir
    if resume.file_path and os.path.exists(resume.file_path):
        try:
            os.remove(resume.file_path)
        except Exception:
            pass

    db.delete(resume)
    db.commit()
    return {"message": f"Currículo #{resume_id} excluído com sucesso"}

