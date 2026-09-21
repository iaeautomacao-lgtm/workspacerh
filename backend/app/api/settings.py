from fastapi import APIRouter
from pydantic import BaseModel, Field
from app.services.llm_service import get_active_ai_provider
from app.services.whatsapp_service import whatsapp_service
import os
from app.services.calendar_service import configured
router=APIRouter(prefix='/settings',tags=['Settings'])
@router.get('/integrations')
def status():
    return {'ai':get_active_ai_provider(),'whatsapp':{'configured':whatsapp_service.configured(),'automatic':os.getenv('WHATSAPP_AUTO_SEND','false').lower()=='true','status':'Configurado; validar com fornecedor' if whatsapp_service.configured() else 'Aguardando API do fornecedor'},'calendar':{'status':'Outlook configurado para consultar disponibilidade' if configured() else 'Agenda interna disponível; Outlook aguarda credenciais'},'database':'MySQL / MariaDB' if os.getenv('DATABASE_URL','').startswith(('mysql','mariadb')) else 'SQLite (desenvolvimento)'}
@router.get('/ai-status')
def ai_status(): return get_active_ai_provider()
