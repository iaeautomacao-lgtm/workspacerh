"""Read-only Outlook availability adapter (Microsoft Graph application credentials)."""
import os
import json
import re
import urllib.request
from urllib.parse import urlencode, quote
from datetime import timezone

class CalendarUnavailable(ValueError): pass

def configured():
    return all(os.getenv(k) for k in ('MS_TENANT_ID','MS_CLIENT_ID','MS_CLIENT_SECRET','MS_RH_MAILBOX'))

def token():
    tenant=os.environ['MS_TENANT_ID']
    if not re.fullmatch(r'[A-Za-z0-9.-]+',tenant): raise CalendarUnavailable('Tenant Microsoft inválido.')
    body=urlencode({'client_id':os.environ['MS_CLIENT_ID'],'client_secret':os.environ['MS_CLIENT_SECRET'],'scope':'https://graph.microsoft.com/.default','grant_type':'client_credentials'}).encode()
    req=urllib.request.Request(f'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token',data=body,headers={'Content-Type':'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req,timeout=15) as response: return json.load(response)['access_token']

def ensure_available(recruiter,start,end):
    if not configured(): return 'local'
    # Limit reads to explicitly authorized mailboxes.
    allowed={v.strip().lower() for v in (os.getenv('MS_ALLOWED_MAILBOXES') or os.environ['MS_RH_MAILBOX']).split(',')}
    if recruiter.lower() not in allowed: raise CalendarUnavailable('Recrutador não está na lista de caixas autorizadas do Microsoft 365.')
    def utc(d): return d.astimezone(timezone.utc).replace(tzinfo=None).isoformat() if d.tzinfo else d.isoformat()
    payload={'schedules':[recruiter],'startTime':{'dateTime':utc(start),'timeZone':'UTC'},'endTime':{'dateTime':utc(end),'timeZone':'UTC'},'availabilityViewInterval':5}
    try:
        req=urllib.request.Request('https://graph.microsoft.com/v1.0/users/'+quote(os.environ['MS_RH_MAILBOX'],safe='')+'/calendar/getSchedule',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+token(),'Content-Type':'application/json','Prefer':'outlook.timezone="UTC"'})
        with urllib.request.urlopen(req,timeout=20) as response: data=json.load(response)
        rows=data.get('value',[])
        if len(rows)!=1 or rows[0].get('error') or 'scheduleItems' not in rows[0]: raise CalendarUnavailable('Outlook não confirmou a disponibilidade. Tente novamente.')
        if any(item.get('status')!='free' for item in rows[0]['scheduleItems']) or any(c!='0' for c in rows[0].get('availabilityView','')): raise CalendarUnavailable('O Outlook indica compromisso ou indisponibilidade neste horário.')
        return 'outlook'
    except CalendarUnavailable: raise
    except Exception: raise CalendarUnavailable('Não foi possível consultar o Outlook. Verifique credenciais e permissões; a reserva não foi confirmada.')
