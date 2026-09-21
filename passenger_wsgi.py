"""cPanel Passenger entry point. Application root must stay outside public_html."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / '.venv'
VENV_PYTHON = VENV / 'bin' / 'python'

# O cPanel nem sempre aplica o interpretador informado no registro do aplicativo:
# o Passenger acaba subindo com o Python do sistema, que não enxerga as
# dependências instaladas no ambiente virtual. Quando isso acontece, trocamos de
# interpretador antes de importar qualquer coisa da aplicação.
# A comparação usa sys.prefix porque .venv/bin/python é um link para o binário do
# sistema — comparar caminhos resolvidos daria falso negativo.
if (VENV_PYTHON.is_file()
        and Path(sys.prefix).resolve() != VENV.resolve()
        and not os.environ.get('RH_VENV_REEXEC')):
    os.environ['RH_VENV_REEXEC'] = '1'
    os.execl(str(VENV_PYTHON), str(VENV_PYTHON), *sys.argv)

sys.path.insert(0, str(ROOT / 'backend'))
from app.main import app
from app.core.database import Base, engine
from a2wsgi import ASGIMiddleware
# Passenger does not run the ASGI lifespan protocol.
Base.metadata.create_all(engine)
application = ASGIMiddleware(app, wait_time=300)
