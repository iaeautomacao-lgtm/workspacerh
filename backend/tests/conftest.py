import os
import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE_URL']='sqlite://'
os.environ['OPENAI_API_KEY']=''
os.environ['COOKIE_SECURE']='false'
os.environ['WHATSAPP_ENABLED']='false'
os.environ['WHATSAPP_WEBHOOK_TOKEN']='test-webhook-secret'
os.environ['MS_TENANT_ID']=''
from app.main import app
from app.core.database import Base,get_db
from app.core.config import settings
from app.core.auth import password_hash
from app.models.workflow import Account
@pytest.fixture
def client(tmp_path):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Factory=sessionmaker(bind=engine)
    def db():
        with Factory() as session: yield session
    app.dependency_overrides[get_db]=db
    previous=settings.UPLOAD_DIR
    settings.UPLOAD_DIR=str(tmp_path)
    with Factory() as session:
        session.add(Account(name='RH Teste',email='rh@example.test',password_hash=password_hash('test-password-123')));session.commit()
    with TestClient(app) as c: yield c
    app.dependency_overrides.clear();settings.UPLOAD_DIR=previous;engine.dispose()
@pytest.fixture
def authenticated(client):
    response=client.post('/api/v1/auth/login',json={'email':'rh@example.test','password':'test-password-123'})
    assert response.status_code==200,response.text
    client.headers['X-Requested-With']='DDM-RH'
    return client
