from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import require_admin, require_rh, password_hash, revoke_sessions
from app.models.domain import AuditLog
from app.models.workflow import Account

router = APIRouter(prefix='/accounts', tags=['Accounts'], dependencies=[Depends(require_admin)])

MIN_PASSWORD = 12

class AccountInput(BaseModel):
    name: str = Field(min_length=3, max_length=190)
    email: str = Field(min_length=5, max_length=190)
    password: str = Field(min_length=MIN_PASSWORD, max_length=200)
    role: Literal['admin', 'rh'] = 'rh'

class AccountEdit(BaseModel):
    name: str = Field(min_length=3, max_length=190)
    role: Literal['admin', 'rh'] = 'rh'
    active: bool = True

class PasswordReset(BaseModel):
    new_password: str = Field(min_length=MIN_PASSWORD, max_length=200)

def serialize(account):
    return {'id': account.id, 'name': account.name, 'email': account.email, 'role': account.role,
            'active': account.active, 'created_at': account.created_at, 'last_login_at': account.last_login_at}

def normalize(email):
    email = email.strip().lower()
    if '@' not in email or ' ' in email:
        raise HTTPException(422, 'Informe um e-mail válido.')
    return email

def admins(db, exceto=None):
    query = db.query(Account).filter(Account.role == 'admin', Account.active == True)
    if exceto:
        query = query.filter(Account.id != exceto)
    return query.count()

@router.get('')
def listing(db: Session = Depends(get_db)):
    return [serialize(a) for a in db.query(Account).order_by(Account.id).all()]

@router.post('')
def create(body: AccountInput, db: Session = Depends(get_db), account=Depends(require_admin)):
    email = normalize(body.email)
    if db.query(Account).filter(Account.email == email).first():
        raise HTTPException(409, 'Já existe uma conta com este e-mail.')
    novo = Account(name=body.name.strip(), email=email, role=body.role, password_hash=password_hash(body.password))
    db.add(novo)
    db.add(AuditLog(company_id=0, user_id=account.id, action='account_created', details=f'email={email} papel={body.role}'))
    db.commit()
    return serialize(novo)

@router.put('/{account_id}')
def update(account_id: int, body: AccountEdit, db: Session = Depends(get_db), account=Depends(require_admin)):
    alvo = db.get(Account, account_id)
    if not alvo:
        raise HTTPException(404, 'Conta não encontrada')
    # Não dá para o último administrador se rebaixar ou se desativar: ninguém mais gerencia acessos.
    perdeu_admin = alvo.role == 'admin' and (body.role != 'admin' or not body.active)
    if perdeu_admin and not admins(db, exceto=alvo.id):
        raise HTTPException(422, 'Esta é a única conta de administrador ativa. Promova outra antes de alterar esta.')
    if alvo.id == account.id and not body.active:
        raise HTTPException(422, 'Você não pode desativar a própria conta.')
    alvo.name = body.name.strip()
    alvo.role = body.role
    desativou = alvo.active and not body.active
    alvo.active = body.active
    if desativou:
        revoke_sessions(db, alvo.id)
    db.add(AuditLog(company_id=0, user_id=account.id, action='account_updated', details=f'conta={alvo.id} papel={body.role} ativa={body.active}'))
    db.commit()
    return serialize(alvo)

@router.post('/{account_id}/password')
def reset(account_id: int, body: PasswordReset, db: Session = Depends(get_db), account=Depends(require_admin)):
    """Redefinição pelo administrador. Todas as sessões da conta caem."""
    alvo = db.get(Account, account_id)
    if not alvo:
        raise HTTPException(404, 'Conta não encontrada')
    alvo.password_hash = password_hash(body.new_password)
    revoke_sessions(db, alvo.id)
    db.add(AuditLog(company_id=0, user_id=account.id, action='account_password_reset', details=f'conta={alvo.id} email={alvo.email}'))
    db.commit()
    return {'ok': True, 'message': f'Senha de {alvo.name} redefinida. Entregue a nova senha pessoalmente e peça a troca no primeiro acesso.'}

@router.delete('/{account_id}')
def remove(account_id: int, db: Session = Depends(get_db), account=Depends(require_admin)):
    alvo = db.get(Account, account_id)
    if not alvo:
        raise HTTPException(404, 'Conta não encontrada')
    if alvo.id == account.id:
        raise HTTPException(422, 'Você não pode excluir a própria conta.')
    if alvo.role == 'admin' and not admins(db, exceto=alvo.id):
        raise HTTPException(422, 'Esta é a única conta de administrador. Promova outra antes de excluir esta.')
    revoke_sessions(db, alvo.id)
    db.add(AuditLog(company_id=0, user_id=account.id, action='account_deleted', details=f'conta={alvo.id} email={alvo.email}'))
    db.delete(alvo)
    db.commit()
    return {'deleted': True}
