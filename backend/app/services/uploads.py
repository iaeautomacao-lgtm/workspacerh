from pathlib import Path
import uuid
import zipfile
from fastapi import HTTPException
from app.core.config import settings
from app.services.resume_parser import extract_text_from_file

async def store_resume(file):
    name=Path((file.filename or '').replace('\\','/')).name
    ext=Path(name).suffix.lower()
    if ext not in ('.pdf','.docx'): raise HTTPException(422,'Envie um PDF ou DOCX.')
    content=await file.read(8*1024*1024+1)
    if len(content)>8*1024*1024: raise HTTPException(413,'O currículo deve ter até 8 MB.')
    if ext=='.pdf' and not content.startswith(b'%PDF-'): raise HTTPException(422,'PDF inválido.')
    path=Path(settings.UPLOAD_DIR)/(uuid.uuid4().hex+ext)
    try:
        path.write_bytes(content)
        if ext=='.docx':
            with zipfile.ZipFile(path) as archive:
                if sum(i.file_size for i in archive.infolist())>32*1024*1024: raise ValueError('Documento muito grande')
        text=extract_text_from_file(str(path))
        if len(text.strip())<40: raise ValueError('Sem texto legível')
        return name,str(path),text[:100000]
    except Exception:
        path.unlink(missing_ok=True)
        raise HTTPException(422,'Não foi possível ler o currículo. Use PDF com texto selecionável ou DOCX.')

def drop_file(path):
    """Remove o arquivo do currículo do disco. Falha silenciosa: o registro é o que importa."""
    try:
        target = Path(path)
        if target.is_file() and target.parent.resolve() == Path(settings.UPLOAD_DIR).resolve():
            target.unlink()
            return True
    except OSError:
        pass
    return False
