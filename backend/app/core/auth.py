from app.core.time import utcnow
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.workflow import Account, LoginSession

router = APIRouter(prefix='/auth', tags=['Authentication'])

def password_hash(password):
    salt = secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return salt + ':' + value

def verify_password(password, stored):
    salt, expected = stored.split(':')
    value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(value, expected)

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def require_rh(request: Request, db: Session = Depends(get_db)):
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.headers.get('X-Requested-With') != 'DDM-RH':
        raise HTTPException(403, 'Requisição não autorizada')
    session = db.get(LoginSession, digest(request.cookies.get('rh_session', '')))
    if not session or session.expires_at <= utcnow():
        raise HTTPException(401, 'Faça login para acessar a área do RH')
    account = db.get(Account, session.account_id)
    if not account:
        raise HTTPException(401, 'Sessão inválida')
    if not account.active:
        raise HTTPException(403, 'Esta conta está desativada. Procure o administrador.')
    return account

def require_admin(account=Depends(require_rh)):
    """Gestão de contas é privativa do administrador."""
    if account.role != 'admin':
        raise HTTPException(403, 'Apenas o administrador gerencia as contas de acesso.')
    return account

def revoke_sessions(db, account_id, keep=None):
    """Derruba as sessões abertas da conta. Usado ao trocar senha ou desativar."""
    query = db.query(LoginSession).filter(LoginSession.account_id == account_id)
    if keep:
        query = query.filter(LoginSession.token_hash != keep)
    total = query.delete(synchronize_session=False)
    return total

class Login(BaseModel):
    email: str = Field(max_length=190)
    password: str = Field(max_length=200)

_attempts = {}
@router.post('/login')
def login(body: Login, request: Request, response: Response, db: Session = Depends(get_db)):
    key = request.client.host if request.client else 'unknown'
    now = utcnow()
    attempts = [t for t in _attempts.get(key, []) if t > now - timedelta(minutes=15)]
    if len(attempts) >= 10:
        raise HTTPException(429, 'Muitas tentativas. Aguarde 15 minutos.')
    _attempts[key] = attempts + [now]
    account = db.query(Account).filter(Account.email == body.email.strip().lower()).first()
    valid = verify_password(body.password, account.password_hash) if account else verify_password(body.password, password_hash('unused'))
    if not account or not valid:
        raise HTTPException(401, 'E-mail ou senha incorretos')
    if not account.active:
        raise HTTPException(403, 'Esta conta está desativada. Procure o administrador.')
    account.last_login_at = now
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=digest(token), account_id=account.id, expires_at=now + timedelta(hours=8)))
    db.commit()
    import os
    response.set_cookie('rh_session', token, httponly=True, secure=os.getenv('COOKIE_SECURE', 'true').lower() == 'true', samesite='strict', max_age=28800)
    _attempts.pop(key, None)
    return {'name': account.name, 'email': account.email}

@router.get('/me')
def me(account=Depends(require_rh)):
    return {'id': account.id, 'name': account.name, 'email': account.email, 'role': account.role}

class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=12, max_length=200)

@router.post('/password')
def change_password(body: PasswordChange, request: Request, account=Depends(require_rh), db: Session = Depends(get_db)):
    """Troca da própria senha. Exige a senha atual e derruba as outras sessões."""
    if not verify_password(body.current_password, account.password_hash):
        raise HTTPException(403, 'Senha atual incorreta.')
    if body.new_password == body.current_password:
        raise HTTPException(422, 'A nova senha precisa ser diferente da atual.')
    account.password_hash = password_hash(body.new_password)
    atual = digest(request.cookies.get('rh_session', ''))
    revoke_sessions(db, account.id, keep=atual)
    db.commit()
    return {'ok': True, 'message': 'Senha alterada. As outras sessões foram encerradas.'}

@router.post('/logout')
def logout(request: Request, response: Response, account=Depends(require_rh), db: Session = Depends(get_db)):
    session = db.get(LoginSession, digest(request.cookies.get('rh_session', '')))
    if session:
        db.delete(session)
        db.commit()
    response.delete_cookie('rh_session')
    return {'ok': True}
