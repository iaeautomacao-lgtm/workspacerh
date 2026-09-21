from app.core.time import utcnow
import os
import hmac
from datetime import datetime, timezone
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.core.auth import require_rh
from app.models.domain import Candidate, Job, Resume, AuditLog
from app.models.workflow import JobPolicy, Conversation, Outbox, IncomingEvent, CalendarSlot
from app.services.whatsapp_service import whatsapp_service, normalize_phone
from app.api.screenings import summary
from app.services.calendar_service import ensure_available, CalendarUnavailable

router=APIRouter(tags=['Workflow'],dependencies=[Depends(require_rh)])
webhooks=APIRouter(prefix='/webhooks',tags=['Provider webhooks'])

class Contact(BaseModel):
    name:str=Field(min_length=2,max_length=190)
    email:Optional[str]=Field(default=None,max_length=190)
    phone:str=Field(max_length=30)
@router.put('/candidates/{candidate_id}')
def contact(candidate_id:int,body:Contact,db:Session=Depends(get_db)):
    candidate=db.get(Candidate,candidate_id)
    if not candidate: raise HTTPException(404,'Candidato não encontrado')
    try: phone=normalize_phone(body.phone)
    except ValueError as e: raise HTTPException(422,str(e))
    candidate.name=body.name;candidate.phone=phone;candidate.email=body.email;db.commit();return {'ok':True}

class Selection(BaseModel):
    candidate_ids:list[int]=Field(min_length=1,max_length=1000)
    reviewed:bool
@router.post('/jobs/{job_id}/shortlist')
def shortlist(job_id:int,body:Selection,db:Session=Depends(get_db),account=Depends(require_rh)):
    job=db.get(Job,job_id);policy=db.get(JobPolicy,job_id)
    if not job or not policy or not policy.openings: raise HTTPException(422,'Confirme a quantidade de vagas primeiro.')
    if not body.reviewed: raise HTTPException(422,'O RH precisa revisar os selecionados.')
    report=summary(job,db)
    if report['stale']: raise HTTPException(409,'Reexecute a análise: os currículos ou requisitos mudaram.')
    ids=set(body.candidate_ids)
    if len(ids)!=len(body.candidate_ids): raise HTTPException(422,'Candidatos duplicados.')
    allowed={r['candidate_id'] for r in report['results']}
    if not ids.issubset(allowed): raise HTTPException(422,'Candidato não pertence à vaga.')
    db.query(Job).filter_by(id=job_id).with_for_update().first()
    existing=db.query(Conversation).filter_by(job_id=job_id).all()
    existing_ids={c.candidate_id for c in existing}
    if len(existing_ids|ids)>policy.openings: raise HTTPException(422,'A seleção excede a quantidade de vagas confirmada.')
    if not policy.questions: raise HTTPException(422,'Cadastre ao menos uma pergunta de triagem nesta vaga.')
    created=0
    for candidate_id in ids-existing_ids:
        candidate=db.get(Candidate,candidate_id)
        try: phone=normalize_phone(candidate.phone)
        except ValueError as e: raise HTTPException(422,f'{candidate.name}: {e}')
        conv=Conversation(candidate_id=candidate_id,job_id=job_id,phone=phone,questions=policy.questions,answers=[])
        db.add(conv);db.flush()
        content=policy.message_template.replace('{nome}',candidate.name).replace('{vaga}',job.title)
        db.add(Outbox(conversation_id=conv.id,content=content,status='pending'));created+=1
    db.add(AuditLog(company_id=job.company_id,user_id=account.id,action='shortlist_reviewed',details=','.join(map(str,sorted(ids)))))
    try: db.commit()
    except IntegrityError: db.rollback();raise HTTPException(409,'A seleção já foi registrada. Atualize a tela.')
    return {'queued':created,'message':'Mensagens preparadas. Revise e envie na aba WhatsApp.'}

@router.get('/conversations')
def conversations(db:Session=Depends(get_db)):
    return [{'id':c.id,'name':db.get(Candidate,c.candidate_id).name,'job':db.get(Job,c.job_id).title,'status':c.status,'phone':c.phone,'questions':c.questions,'answers':c.answers,'messages':[{'id':m.id,'content':m.content,'status':m.status,'error':m.error} for m in db.query(Outbox).filter_by(conversation_id=c.id).order_by(Outbox.id).all()]} for c in db.query(Conversation).order_by(Conversation.id.desc()).all()]

@router.post('/outbox/{message_id}/send')
def dispatch(message_id:int,db:Session=Depends(get_db)):
    if not whatsapp_service.configured(): raise HTTPException(409,'WhatsApp aguarda integração e homologação com o fornecedor.')
    claimed=db.query(Outbox).filter(Outbox.id==message_id,Outbox.status=='pending').update({'status':'sending'})
    db.commit()
    if not claimed: raise HTTPException(409,'Mensagem já processada ou aguardando conciliação com o provedor.')
    msg=db.get(Outbox,message_id);conv=db.get(Conversation,msg.conversation_id)
    if conv.status=='opted_out': msg.status='cancelled';db.commit();raise HTTPException(409,'Candidato encerrou o contato.')
    try:
        msg.provider_id=whatsapp_service.send(conv.phone,msg.content,msg.id);msg.status='accepted'
    except Exception:
        msg.status='uncertain';msg.error='Envio sem confirmação. Consulte o provedor antes de reenviar para evitar duplicidade.'
    db.commit();return {'status':msg.status,'error':msg.error}

class Event(BaseModel):
    event_id:str=Field(min_length=1,max_length=190)
    conversation_id:int
    text:str=Field(min_length=1,max_length=4000)
    phone:str=Field(max_length=30)
@webhooks.post('/whatsapp')
def incoming(body:Event,x_webhook_token:str=Header(default=''),db:Session=Depends(get_db)):
    token=os.getenv('WHATSAPP_WEBHOOK_TOKEN','')
    if not token or not hmac.compare_digest(token,x_webhook_token): raise HTTPException(401,'Token inválido')
    if db.get(IncomingEvent,body.event_id): return {'duplicate':True}
    conv=db.query(Conversation).filter_by(id=body.conversation_id).with_for_update().first()
    if not conv: raise HTTPException(404,'Conversa não encontrada')
    try: phone=normalize_phone(body.phone)
    except ValueError: raise HTTPException(422,'Telefone inválido')
    if phone!=conv.phone: raise HTTPException(403,'Telefone divergente')
    db.add(IncomingEvent(event_id=body.event_id))
    answer=body.text.strip();reply=None
    if answer.upper() in ('SAIR','PARAR','CANCELAR'):
        conv.status='opted_out'
        db.query(Outbox).filter_by(conversation_id=conv.id,status='pending').update({'status':'cancelled'})
    elif conv.status=='awaiting_consent':
        if answer.upper() in ('SIM','ACEITO'):
            conv.status='screening';reply=conv.questions[0] if conv.questions else None
            if not reply: conv.status='completed'
        else: reply='Responda SIM para iniciar a triagem ou SAIR para encerrar.'
    elif conv.status=='screening':
        responses=list(conv.answers or []);responses.append({'question':conv.questions[len(responses)],'answer':answer})
        conv.answers=responses
        if len(responses)<len(conv.questions): reply=conv.questions[len(responses)]
        else: conv.status='completed';reply='Obrigado! Suas respostas foram encaminhadas ao RH. Aguarde o retorno da equipe.'
    if reply: db.add(Outbox(conversation_id=conv.id,content=reply))
    try: db.commit()
    except IntegrityError: db.rollback();return {'duplicate':True}
    return {'ok':True,'status':conv.status}

class SlotInput(BaseModel):
    recruiter:str=Field(min_length=2,max_length=190)
    starts_at:datetime
    ends_at:datetime
    location:str=Field(min_length=2,max_length=255)
@router.post('/calendar/slots')
def create_slot(body:SlotInput,db:Session=Depends(get_db)):
    if not body.starts_at.tzinfo or not body.ends_at.tzinfo: raise HTTPException(422,'Informe horários com fuso.')
    start=body.starts_at.astimezone(timezone.utc).replace(tzinfo=None);end=body.ends_at.astimezone(timezone.utc).replace(tzinfo=None)
    if end<=start or start<=utcnow(): raise HTTPException(422,'Use um intervalo futuro válido.')
    # Serialize agenda writes across workers using the authenticated RH account row.
    from app.models.workflow import Account
    db.query(Account).order_by(Account.id).with_for_update().all()
    if db.query(CalendarSlot).filter(CalendarSlot.recruiter==body.recruiter,CalendarSlot.starts_at<end,CalendarSlot.ends_at>start).first(): raise HTTPException(409,'O recrutador já possui um horário neste intervalo.')
    try: ensure_available(body.recruiter,start,end)
    except CalendarUnavailable as e: raise HTTPException(409,str(e))
    slot=CalendarSlot(recruiter=body.recruiter,starts_at=start,ends_at=end,location=body.location);db.add(slot);db.commit();return {'id':slot.id}

@router.get('/calendar/slots')
def slots(db:Session=Depends(get_db)):
    return [{'id':s.id,'recruiter':s.recruiter,'starts_at':s.starts_at.isoformat()+'Z','ends_at':s.ends_at.isoformat()+'Z','location':s.location,'conversation_id':s.conversation_id} for s in db.query(CalendarSlot).order_by(CalendarSlot.starts_at).all()]
class Booking(BaseModel):
    conversation_id:int
@router.post('/calendar/slots/{slot_id}/book')
def book(slot_id:int,body:Booking,db:Session=Depends(get_db)):
    conv=db.query(Conversation).filter_by(id=body.conversation_id).with_for_update().first()
    if not conv or conv.status!='completed': raise HTTPException(422,'Finalize a triagem antes de agendar.')
    slot=db.get(CalendarSlot,slot_id)
    if not slot: raise HTTPException(404,'Horário não encontrado')
    try: ensure_available(slot.recruiter,slot.starts_at,slot.ends_at)
    except CalendarUnavailable as e: raise HTTPException(409,str(e))
    try:
        count=db.query(CalendarSlot).filter(CalendarSlot.id==slot_id,CalendarSlot.conversation_id==None,CalendarSlot.starts_at>utcnow()).update({'conversation_id':conv.id})
        if not count: raise HTTPException(409,'Horário indisponível.')
        conv.status='interview_scheduled';db.commit()
    except IntegrityError: db.rollback();raise HTTPException(409,'O candidato já tem entrevista marcada.')
    return {'ok':True}
