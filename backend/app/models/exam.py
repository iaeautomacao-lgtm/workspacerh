from app.core.time import utcnow
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint, Index
from app.core.database import Base

KINDS = ('choice', 'truefalse', 'matching', 'essay')
OBJECTIVE = ('choice', 'truefalse', 'matching')

MODES = ('online', 'presencial')

class Exam(Base):
    __tablename__ = 'exams'
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('jobs.id'), nullable=True, index=True)
    title = Column(String(190), nullable=False)
    instructions = Column(Text, default='')
    duration_minutes = Column(Integer, nullable=False, default=60)
    open = Column(Boolean, default=False, nullable=False)
    # Perfil da prova, usado para montar a partir da biblioteca e para filtrar.
    level = Column(String(20), default='junior', nullable=False)
    area = Column(String(120), default='')
    mode = Column(String(20), default='online', nullable=False)
    # Código exigido do candidato na prova online. Vazio deixa a prova aberta a quem tem o link.
    access_code = Column(String(40), default='')
    created_at = Column(DateTime, default=utcnow)

class ExamQuestion(Base):
    __tablename__ = 'exam_questions'
    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey('exams.id'), nullable=False, index=True)
    position = Column(Integer, nullable=False, default=0)
    kind = Column(String(20), nullable=False)
    statement = Column(Text, nullable=False)
    weight = Column(Float, nullable=False, default=1.0)
    # Público: alternativas exibidas ao candidato.
    options = Column(JSON, default=list)
    # Privado: nunca serializado para o candidato. Ver api.exams.public_question.
    answer_key = Column(JSON, nullable=True)
    rubric = Column(JSON, default=list)

class ExamAttempt(Base):
    __tablename__ = 'exam_attempts'
    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey('exams.id'), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey('jobs.id'), nullable=True, index=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id'), nullable=True, index=True)
    token_hash = Column(String(64), unique=True, nullable=False)
    name = Column(String(190), nullable=False)
    email = Column(String(190))
    phone = Column(String(30))
    document = Column(String(40))
    started_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    submitted_at = Column(DateTime)
    status = Column(String(20), default='in_progress', nullable=False)
    objective_score = Column(Float)
    final_score = Column(Float)
    __table_args__ = (Index('ix_exam_attempts_job_candidate', 'job_id', 'candidate_id'),)

class ExamAnswer(Base):
    __tablename__ = 'exam_answers'
    id = Column(Integer, primary_key=True)
    attempt_id = Column(Integer, ForeignKey('exam_attempts.id'), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey('exam_questions.id'), nullable=False)
    response = Column(JSON, nullable=True)
    correct = Column(Boolean, nullable=True)
    awarded = Column(Float, nullable=True)
    ai_suggestion = Column(JSON, nullable=True)
    reviewer_note = Column(Text)
    __table_args__ = (UniqueConstraint('attempt_id', 'question_id'),)
