import os
import sys

# Garante que a pasta 'backend' esteja no PYTHONPATH para resolver o pacote 'app'
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.database import engine, Base
from app.api import jobs, resumes, screenings, messages, settings

# Cria as tabelas do banco de dados na inicialização
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Plataforma Universal de Recrutamento com IA - Grupo DDM",
    version="1.0.0"
)

# Inclui os roteadores da API REST com o prefixo /api/v1
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(resumes.router, prefix="/api/v1")
app.include_router(screenings.router, prefix="/api/v1")
app.include_router(messages.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")



# Caminho para o frontend index.html
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

@app.get("/", response_class=FileResponse)
def serve_index():
    index_path = os.path.join(ROOT_DIR, "index.html")
    return FileResponse(index_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
