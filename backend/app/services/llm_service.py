import os
import json
import urllib.request
import re
from typing import Dict, Any, Optional

def load_env_keys():
    """Carrega as chaves do arquivo .env se existirem."""
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

def get_active_ai_provider() -> Dict[str, Any]:
    load_env_keys()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()

    if gemini_key:
        return {"provider": "gemini", "active": True, "model": "Gemini 1.5 Flash"}
    elif openai_key:
        return {"provider": "openai", "active": True, "model": "GPT-4o-mini"}
    elif groq_key:
        return {"provider": "groq", "active": True, "model": "Llama-3.3-70B"}
    return {"provider": "none", "active": False, "model": "Motor Determinístico Local"}

def call_gemini(api_key: str, prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.2
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as res:
        res_json = json.loads(res.read().decode("utf-8"))
        return res_json["candidates"][0]["content"]["parts"][0]["text"]

def call_openai_compatible(api_url: str, api_key: str, model: str, prompt: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Você é um especialista em RH e triagem de currículos que responde SEMPRE e EXCLUSIVAMENTE em formato JSON válido."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(api_url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    })
    with urllib.request.urlopen(req, timeout=30) as res:
        res_json = json.loads(res.read().decode("utf-8"))
        return res_json["choices"][0]["message"]["content"]

def evaluate_with_ai(job_title: str, job_description: str, resume_text: str, candidate_name: str) -> Optional[Dict[str, Any]]:
    load_env_keys()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()

    if not (gemini_key or openai_key or groq_key):
        return None  # Nenhuma chave configurada, usa motor local

    prompt = f"""
Você é o Avaliador Chefe de Recrutamento & Seleção do Grupo DDM.
Avalie com profundo rigor técnico e evidências reais a aderência do candidato abaixo para a vaga especificada.

=== DADOS DA VAGA ===
Título: {job_title}
Descrição e Requisitos:
{job_description[:4000]}

=== CURRÍCULO DO CANDIDATO ({candidate_name}) ===
{resume_text[:6000]}

=== INSTRUÇÃO DE PONTUAÇÃO (Padrão DDM 60/20/10/10) ===
1. Obrigatórios (60% da nota): Avalie cada requisito obrigatório da vaga (ex: formação, experiência chave, modalidade presencial). Cite trechos do currículo.
2. Desejáveis (20% da nota): Avalie conhecimentos complementares, sistemas, legislações, ferramentas.
3. Experiência (10% da nota): Calcule tempo total e nível de maturidade (Júnior, Pleno, Sênior).
4. Competências (10% da nota): Avalie soft skills demonstradas.

Retorne EXCLUSIVAMENTE um objeto JSON no seguinte formato:
{{
  "score": <número float de 0 a 100 calculado pela soma dos 4 blocos>,
  "status": "<'Alta aderência' se score >= 80, senão 'Requer análise'>",
  "mandatory_matched": "<ex: '3/3 atendidos' ou '2/3 atendidos'>",
  "experience": "<ex: '7 anos (Sênior)' ou '3 anos (Pleno)'>",
  "summary": "<breve parecer técnico de 2 frases>",
  "evidences": [
    {{
      "category": "OBRIGATÓRIO",
      "req": "<descrição do requisito>",
      "status": "<Atende ou Não Atende>",
      "detail": "<evidência exata extraída do currículo ou motivo do não atendimento>"
    }},
    {{
      "category": "DESEJÁVEL",
      "req": "<descrição do requisito>",
      "status": "<Atende ou Não Atende>",
      "detail": "<evidência extraída do currículo>"
    }},
    {{
      "category": "EXPERIÊNCIA",
      "req": "Tempo e Profundidade de Atuação",
      "status": "<Atende ou Não Atende>",
      "detail": "<análise detalhada do histórico profissional>"
    }},
    {{
      "category": "COMPETÊNCIA",
      "req": "Perfil e Competências",
      "status": "<Atende ou Não Atende>",
      "detail": "<análise comportamental observada no currículo>"
    }}
  ]
}}
"""
    try:
        raw_response = ""
        if gemini_key:
            raw_response = call_gemini(gemini_key, prompt)
        elif groq_key:
            raw_response = call_openai_compatible("https://api.groq.com/openai/v1/chat/completions", groq_key, "llama-3.3-70b-versatile", prompt)
        elif openai_key:
            raw_response = call_openai_compatible("https://api.openai.com/v1/chat/completions", openai_key, "gpt-4o-mini", prompt)

        # Limpa blocos de markdown ```json se presentes
        clean_json = re.sub(r'^```json\s*', '', raw_response.strip(), flags=re.MULTILINE)
        clean_json = re.sub(r'```$', '', clean_json.strip(), flags=re.MULTILINE)
        
        parsed = json.loads(clean_json)
        
        # Formata para o padrão esperado pelo frontend
        ev_list = parsed.get("evidences", [])
        return {
            "candidate_name": candidate_name,
            "score": float(parsed.get("score", 0)),
            "mandatory_matched": parsed.get("mandatory_matched", "2/2 atendidos"),
            "experience": parsed.get("experience", "1 ano"),
            "status": parsed.get("status", "Alta aderência"),
            "evidences": {
                "all": ev_list,
                "mandatory": [e for e in ev_list if e.get("category") == "OBRIGATÓRIO"],
                "summary": parsed.get("summary", "")
            }
        }
    except Exception as e:
        print(f"[ERRO LLM] Falha ao processar com IA: {e}")
        return None
