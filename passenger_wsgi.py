"""cPanel Passenger entry point. Application root must stay outside public_html."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'backend'))
from app.main import app
from app.core.database import Base,engine
from a2wsgi import ASGIMiddleware
# Passenger does not run the ASGI lifespan protocol.
Base.metadata.create_all(engine)
application=ASGIMiddleware(app,wait_time=300)
