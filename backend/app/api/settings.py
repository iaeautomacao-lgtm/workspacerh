import os
from fastapi import APIRouter
from pydantic import BaseModel
from app.services.llm_service import get_active_ai_provider, load_env_keys

router = APIRouter(prefix="/settings", tags=["Settings"])

class AIKeyPayload(BaseModel):
    provider: str # 'gemini', 'openai', 'groq'
    api_key: str

@router.get("/ai-status")
def get_ai_status():
    return get_active_ai_provider()

@router.post("/ai-key")
def save_ai_key(payload: AIKeyPayload):
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
    
    key_map = {
        "gemini": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "groq": "GROQ_API_KEY"
    }
    
    env_var_name = key_map.get(payload.provider.lower(), "GEMINI_API_KEY")
    
    # Atualiza o arquivo .env
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    found = False
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{env_var_name}="):
            new_lines.append(f"{env_var_name}={payload.api_key.strip()}\n")
            found = True
        else:
            new_lines.append(line)
            
    if not found:
        new_lines.append(f"{env_var_name}={payload.api_key.strip()}\n")
        
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
        
    os.environ[env_var_name] = payload.api_key.strip()
    load_env_keys()
    
    return {
        "message": f"Chave de API para {payload.provider.upper()} configurada com sucesso!",
        "status": get_active_ai_provider()
    }
