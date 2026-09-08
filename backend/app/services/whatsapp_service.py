import hashlib
from typing import Dict, Any

class WhatsAppService:
    """
    Serviço desacoplado para integração de mensagens via WhatsApp API (Z-API / Evolution API / Twilio / Custom Webhook).
    Permite alterar o provedor sem refazer as regras de negócio da aplicação.
    """
    def __init__(self, provider_url: str = None, api_token: str = None):
        self.provider_url = provider_url
        self.api_token = api_token

    def send_convocation(self, candidate_name: str, job_title: str, phone: str = None) -> Dict[str, Any]:
        hash_token = hashlib.md5(candidate_name.encode()).hexdigest()[:8]
        scheduling_link = f"http://127.0.0.1:8000/agenda/{hash_token}"
        
        message_body = (
            f"Olá {candidate_name}, parabéns! Seu perfil para a vaga de '{job_title}' "
            f"no Grupo DDM foi selecionado na triagem inicial. "
            f"Por favor, escolha o melhor horário para sua entrevista no link a seguir: {scheduling_link}"
        )
        
        # Simula resposta do provedor de mensageria WhatsApp
        return {
            "status": "success",
            "message_id": f"msg_wa_{hash_token}",
            "content": message_body,
            "scheduling_link": scheduling_link
        }

whatsapp_service = WhatsAppService()
