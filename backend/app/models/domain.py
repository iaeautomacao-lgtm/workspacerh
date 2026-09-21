from app.core.time import utcnow
import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utcnow)
    
    users = relationship("User", back_populates="company")
    jobs = relationship("Job", back_populates="company")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    role = Column(String(255), default="recruiter")
    
    company = relationship("Company", back_populates="users")

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    
    company = relationship("Company", back_populates="jobs")
    requirements = relationship("JobRequirement", back_populates="job", cascade="all, delete-orphan")
    resumes = relationship("Resume", back_populates="job", cascade="all, delete-orphan")
    screenings = relationship("Screening", back_populates="job", cascade="all, delete-orphan")

class JobRequirement(Base):
    __tablename__ = "job_requirements"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    category = Column(String(255), nullable=False) # 'mandatory', 'desirable', 'experience', 'competency'
    title = Column(Text, nullable=False)
    weight = Column(Float, default=1.0)
    
    job = relationship("Job", back_populates="requirements")

class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(255), nullable=True)
    
    resumes = relationship("Resume", back_populates="candidate")

class Resume(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(255), nullable=False)
    extracted_text = Column(Text, nullable=False)
    structured_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    
    candidate = relationship("Candidate", back_populates="resumes")
    job = relationship("Job", back_populates="resumes")
    screening_results = relationship("ScreeningResult", back_populates="resume", cascade="all, delete-orphan")

class Screening(Base):
    __tablename__ = "screenings"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    run_at = Column(DateTime, default=utcnow)
    status = Column(String(255), default="completed")
    
    job = relationship("Job", back_populates="screenings")
    results = relationship("ScreeningResult", back_populates="screening", cascade="all, delete-orphan")

class ScreeningResult(Base):
    __tablename__ = "screening_results"
    id = Column(Integer, primary_key=True, index=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"), nullable=False)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=False)
    score = Column(Float, nullable=False)
    mandatory_matched = Column(String(255), nullable=False)
    experience_summary = Column(Text, nullable=False)
    status = Column(String(255), nullable=False)
    evidences = Column(JSON, nullable=True)
    
    screening = relationship("Screening", back_populates="results")
    resume = relationship("Resume", back_populates="screening_results")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    phone_number = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    status = Column(String(255), default="sent") # 'sent', 'delivered', 'read'
    sent_at = Column(DateTime, default=utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=True)
    action = Column(String(255), nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=utcnow)

