from app.core.time import utcnow
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey, UniqueConstraint
from app.core.database import Base

ROLES = ('admin', 'rh')

class Account(Base):
    __tablename__ = 'rh_accounts'
    id = Column(Integer, primary_key=True)
    email = Column(String(190), unique=True, nullable=False)
    name = Column(String(190), nullable=False)
    password_hash = Column(String(255), nullable=False)
    # 'admin' administra as contas; 'rh' usa o sistema sem gerenciar acessos.
    role = Column(String(20), default='rh', nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    last_login_at = Column(DateTime)

class LoginSession(Base):
    __tablename__ = 'rh_sessions'
    token_hash = Column(String(64), primary_key=True)
    account_id = Column(Integer, ForeignKey('rh_accounts.id'), nullable=False)
    expires_at = Column(DateTime, nullable=False)

class JobPolicy(Base):
    __tablename__ = 'job_policies'
    job_id = Column(Integer, ForeignKey('jobs.id'), primary_key=True)
    source_url = Column(Text)
    openings = Column(Integer, nullable=True)
    internal = Column(Boolean, default=False, nullable=False)
    published = Column(Boolean, default=False, nullable=False)
    location = Column(String(190), default='A combinar')
    questions = Column(JSON, default=list)
    message_template = Column(Text, default='Olá, {nome}! Aqui é o RH do Grupo DDM. Você tem interesse em conversar sobre a vaga {vaga}? Responda SIM para iniciar ou SAIR para encerrar.')

class Talent(Base):
    __tablename__ = 'internal_talents'
    id = Column(Integer, primary_key=True)
    name = Column(String(190), nullable=False)
    email = Column(String(190), nullable=False)
    phone = Column(String(30), nullable=False)
    employee_id = Column(String(100), nullable=False)
    department = Column(String(190), nullable=False)
    current_role = Column(String(190), nullable=False)
    interests = Column(Text)
    file_name = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    extracted_text = Column(Text, nullable=False)
    consent_at = Column(DateTime, default=utcnow, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    update_token_hash = Column(String(64), unique=True, nullable=False)

class InternalApplication(Base):
    __tablename__ = 'internal_applications'
    id = Column(Integer, primary_key=True)
    talent_id = Column(Integer, ForeignKey('internal_talents.id'), nullable=False)
    job_id = Column(Integer, ForeignKey('jobs.id'), nullable=False)
    resume_id = Column(Integer, ForeignKey('resumes.id'))
    created_at = Column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('talent_id', 'job_id'),)

class Conversation(Base):
    __tablename__ = 'triage_conversations'
    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id'), nullable=False)
    job_id = Column(Integer, ForeignKey('jobs.id'), nullable=False)
    phone = Column(String(30), nullable=False)
    status = Column(String(40), default='awaiting_consent', nullable=False)
    questions = Column(JSON, default=list)
    answers = Column(JSON, default=list)
    created_at = Column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('candidate_id', 'job_id'),)

class Outbox(Base):
    __tablename__ = 'message_outbox'
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey('triage_conversations.id'), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(40), default='pending', nullable=False)
    provider_id = Column(String(190))
    error = Column(Text)
    created_at = Column(DateTime, default=utcnow)

class IncomingEvent(Base):
    __tablename__ = 'whatsapp_events'
    event_id = Column(String(190), primary_key=True)
    received_at = Column(DateTime, default=utcnow)

class CalendarSlot(Base):
    __tablename__ = 'calendar_slots'
    id = Column(Integer, primary_key=True)
    recruiter = Column(String(190), nullable=False)
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=False)
    location = Column(String(255), nullable=False)
    conversation_id = Column(Integer, ForeignKey('triage_conversations.id'), unique=True)
