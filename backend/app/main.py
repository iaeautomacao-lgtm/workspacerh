import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager
backend_dir=Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path: sys.path.insert(0,str(backend_dir))
from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.database import engine, Base
from app.models import domain,workflow as workflow_models,exam as exam_models
from app.core.auth import router as auth_router, require_rh
from app.api import jobs,resumes,screenings,settings,talents,workflow,exams,accounts
ROOT=backend_dir.parent
@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(bind=engine)
    yield
app=FastAPI(title='DDM Pessoas • Recrutamento e seleção',version='2.0.0',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
app.include_router(auth_router,prefix='/api/v1')
for router in (jobs.router,resumes.router,screenings.router,settings.router):
    app.include_router(router,prefix='/api/v1',dependencies=[Depends(require_rh)])
for router in (talents.public,talents.private,workflow.router,workflow.webhooks,exams.private,exams.public,accounts.router): app.include_router(router,prefix='/api/v1')
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
@app.middleware('http')
async def headers(request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    response.headers['Cache-Control']='no-store'
    return response
@app.get('/')
@app.get('/interno')
@app.get('/login')
@app.get('/prova')
def frontend(): return FileResponse(ROOT/'index.html')
@app.get('/health')
def health(): return {'status':'ok'}
