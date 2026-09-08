import os
import fitz  # PyMuPDF
import docx

def parse_pdf(file_path: str) -> str:
    """Extrai todo o conteúdo textual de um arquivo PDF usando PyMuPDF."""
    text_content = []
    doc = fitz.open(file_path)
    for page in doc:
        text_content.append(page.get_text())
    doc.close()
    return "\n".join(text_content).strip()

def parse_docx(file_path: str) -> str:
    """Extrai todo o conteúdo textual de um arquivo Word DOCX."""
    doc = docx.Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs).strip()

def extract_text_from_file(file_path: str) -> str:
    """Detecta a extensão do arquivo e executa a extração textual real."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return parse_pdf(file_path)
    elif ext in [".docx", ".doc"]:
        return parse_docx(file_path)
    else:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
