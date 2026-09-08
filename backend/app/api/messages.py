from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from app.core.database import get_db
from app.models.domain import Candidate, Job, Message
from app.services.whatsapp_service import whatsapp_service

router = APIRouter(prefix="/candidates", tags=["Messages"])

class WhatsAppSendRequest(BaseModel):
    job_id: int
    phone: Optional[str] = None

class MessageResponse(BaseModel):
    id: int
    candidate_id: int
    job_id: int
    phone_number: Optional[str]
    content: str
    status: str
    sent_at: datetime
    class Config:
        from_attributes = True

@router.post("/{candidate_id}/whatsapp/send", response_model=MessageResponse)
def send_whatsapp_message(candidate_id: int, payload: WhatsAppSendRequest, db: Session = Depends(get_db)):
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        # Se for ID derivado de teste/resume, cria ou busca o candidato
        candidate = Candidate(company_id=1, name=f"Candidato #{candidate_id}")
        db.add(candidate)
        db.commit()
        db.refresh(candidate)

    job = db.query(Job).filter(Job.id == payload.job_id).first()
    job_title = job.title if job else "Vaga Operacional"

    # Envia via WhatsApp Service
    send_result = whatsapp_service.send_convocation(candidate.name, job_title, payload.phone)

    # Registra no histórico do banco de dados
    msg = Message(
        candidate_id=candidate.id,
        job_id=payload.job_id,
        phone_number=payload.phone or "(27) 99999-0000",
        content=send_result["content"],
        status="sent"
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return msg

@router.get("/{candidate_id}/messages", response_model=List[MessageResponse])
def get_candidate_messages(candidate_id: int, db: Session = Depends(get_db)):
    return db.query(Message).filter(Message.candidate_id == candidate_id).order_by(Message.sent_at.desc()).all()
