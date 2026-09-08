import os

class Settings:
    PROJECT_NAME: str = "Plataforma Universal de Recrutamento IA"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./rh_database.db")
    UPLOAD_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))

settings = Settings()
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
