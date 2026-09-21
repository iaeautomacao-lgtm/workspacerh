import os
import re
import json
import urllib.request
from urllib.parse import urlsplit

class WhatsAppService:
    """Generic adapter contract. Enable only after the supplier validates this contract."""
    def configured(self):
        return bool(os.getenv('WHATSAPP_API_URL') and os.getenv('WHATSAPP_API_TOKEN') and os.getenv('WHATSAPP_ENABLED','false').lower()=='true')
    def send(self,phone,content,key):
        if not self.configured(): raise ValueError('Integração WhatsApp pendente. Nenhum envio realizado.')
        url=os.environ['WHATSAPP_API_URL']
        if urlsplit(url).scheme!='https': raise ValueError('O endereço do provedor precisa usar HTTPS.')
        payload={'to':phone,'text':content,'client_reference':str(key)}
        req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['WHATSAPP_API_TOKEN'],'Idempotency-Key':str(key)})
        # Do not forward secrets to redirects.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs): return None
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=20) as response:
            data=json.loads(response.read(65536))
        if not data.get('message_id'): raise ValueError('Provedor não confirmou o identificador da mensagem.')
        return str(data['message_id'])

def normalize_phone(value):
    digits=re.sub(r'\D','',value or '')
    if len(digits) in (10,11): digits='55'+digits
    if not re.fullmatch(r'55\d{10,11}',digits): raise ValueError('Informe um WhatsApp brasileiro válido, com DDD.')
    return digits
whatsapp_service=WhatsAppService()
