import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.engine import make_url
ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env", override=False)

class Settings:
    PROJECT_NAME: str = "Plataforma Universal de Recrutamento IA"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///" + (ROOT / "rh_database.db").as_posix())
    UPLOAD_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))

settings = Settings()
db_url = make_url(settings.DATABASE_URL)
if db_url.drivername == "sqlite" and db_url.database and db_url.database != ":memory:" and not Path(db_url.database).is_absolute():
    settings.DATABASE_URL = db_url.set(database=str((ROOT / db_url.database).resolve())).render_as_string(hide_password=False)
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
