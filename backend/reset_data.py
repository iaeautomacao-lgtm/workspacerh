"""Zera os dados operacionais, preservando as contas de acesso do RH.

Uso, a partir da raiz do projeto:
    python backend/reset_data.py --confirmar

Apaga vagas, candidatos, currículos (inclusive os arquivos em disco), análises,
provas, conversas, agenda e banco de talentos. Não toca em `rh_accounts`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.models import domain, workflow, exam

# Ordem de filho para pai: respeita as chaves estrangeiras.
ORDER = [
    exam.ExamAnswer, exam.ExamAttempt, exam.ExamQuestion, exam.Exam,
    workflow.CalendarSlot, workflow.Outbox, workflow.IncomingEvent, workflow.Conversation,
    workflow.InternalApplication, workflow.Talent,
    domain.ScreeningResult, domain.Screening, domain.Message,
    domain.Resume, domain.Candidate,
    domain.JobRequirement, workflow.JobPolicy, domain.Job,
    domain.AuditLog, domain.User, domain.Company,
]

def wipe():
    Base.metadata.create_all(engine)
    apagados = {}
    with SessionLocal() as db:
        for model in ORDER:
            total = db.query(model).delete(synchronize_session=False)
            if total:
                apagados[model.__tablename__] = total
        db.commit()
    arquivos = 0
    uploads = Path(settings.UPLOAD_DIR)
    if uploads.is_dir():
        for item in uploads.iterdir():
            if item.is_file():
                item.unlink()
                arquivos += 1
    return apagados, arquivos

if __name__ == '__main__':
    if '--confirmar' not in sys.argv:
        raise SystemExit('Isto apaga TODOS os dados operacionais. Rode de novo com --confirmar para prosseguir.')
    apagados, arquivos = wipe()
    if apagados:
        for tabela, total in apagados.items():
            print(f'  {tabela:24} {total} registro(s)')
    else:
        print('  nada a apagar')
    print(f'  arquivos de currículo removidos: {arquivos}')
    with SessionLocal() as db:
        contas = db.query(workflow.Account).count()
    print(f'  contas de acesso preservadas: {contas}')
