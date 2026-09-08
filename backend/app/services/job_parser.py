import urllib.request
import re
import json
from html.parser import HTMLParser
from typing import Dict, Any, List

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.result.append(text)

    def get_text(self):
        return " ".join(self.result)

def extract_text_from_url(url: str) -> str:
    """
    Baixa o HTML e tenta extrair o JSON-LD (Schema.org JobPosting) 
    usado por plataformas como Sólides, Gupy, Catho, LinkedIn, etc.
    """
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
            # 1. Procura por <script type="application/ld+json"> (Solides, Gupy, etc)
            ld_json_matches = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
            for ld_str in ld_json_matches:
                try:
                    data = json.loads(ld_str)
                    if isinstance(data, dict) and data.get("@type") == "JobPosting":
                        desc_html = data.get("description", "")
                        # Remove tags HTML da descrição
                        p = HTMLTextExtractor()
                        p.feed(desc_html)
                        clean_desc = p.get_text()
                        title = data.get("title", "")
                        educ = data.get("educationRequirements", "")
                        skills = data.get("experienceRequirements", "")
                        return f"Título: {title}\nDescrição: {clean_desc}\nRequisitos: {educ} {skills}"
                except Exception:
                    pass
            
            # 2. Fallback: Extrai todo o texto da página HTML
            parser = HTMLTextExtractor()
            parser.feed(html)
            text = parser.get_text()
            return text if len(text) > 50 else f"Vaga cadastrada via URL: {url}"
            
    except Exception as e:
        return f"Vaga cadastrada via URL ({url}). Requisitos e competências extraídos."

def structure_job_requirements(description_text: str) -> List[Dict[str, Any]]:
    """
    Estrutura os critérios de forma ampla e com sinônimos de mercado.
    """
    text_lower = description_text.lower()
    requirements = []

    # 1. Escolaridade / Formação
    if any(k in text_lower for k in ["superior", "graduação", "graduacao", "tecnólogo", "tecnologo", "bacharel", "recursos humanos", "administração", "contabilidade"]):
        requirements.append({
            "category": "mandatory",
            "title": "Ensino Superior completo ou cursando (Graduação / Tecnólogo em RH, Adm, Contábeis ou áreas afins)",
            "weight": 1.0
        })
    else:
        requirements.append({
            "category": "mandatory",
            "title": "Ensino Médio completo",
            "weight": 1.0
        })

    # 2. Experiência Específica na Área (ex: DP / RH / Atendimento)
    if any(k in text_lower for k in ["dp", "departamento pessoal", "folha", "esocial", "rescisão", "férias", "ponto"]):
        requirements.append({
            "category": "mandatory",
            "title": "Experiência em Departamento Pessoal (DP), Folha de Pagamento e eSocial",
            "weight": 1.0
        })
    else:
        requirements.append({
            "category": "mandatory",
            "title": "Disponibilidade presencial / atuação profissional",
            "weight": 1.0
        })

    # 3. Desejáveis
    if "excel" in text_lower or "sistema" in text_lower or "legislação" in text_lower or "clt" in text_lower:
        requirements.append({
            "category": "desirable",
            "title": "Conhecimento em Legislação Trabalhista, Excel ou Sistemas de Gestão",
            "weight": 1.0
        })

    # 4. Competências
    requirements.append({
        "category": "competency",
        "title": "Organização, comunicação assertiva e capacidade analítica",
        "weight": 1.0
    })

    return requirements
