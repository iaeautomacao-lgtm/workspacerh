"""Run from project root: python backend/create_admin.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import getpass
from app.core.database import Base, engine, SessionLocal
from app.models import domain, workflow
from app.core.auth import password_hash
Base.metadata.create_all(engine)
email = input('E-mail do RH: ').strip().lower()
name = input('Nome: ').strip()
password = getpass.getpass('Senha (mínimo 12 caracteres): ')
if '@' not in email or not name or len(password) < 12:
    raise SystemExit('Dados inválidos. Use e-mail válido e senha com 12 caracteres ou mais.')
with SessionLocal() as db:
    if db.query(workflow.Account).filter_by(email=email).first():
        raise SystemExit('Conta já existe. Nenhuma alteração realizada.')
    db.add(workflow.Account(email=email, name=name, role='admin', password_hash=password_hash(password)))
    db.commit()
print('Conta criada.')
