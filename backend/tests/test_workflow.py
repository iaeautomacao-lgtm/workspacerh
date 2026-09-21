from datetime import datetime,timedelta,timezone
import io
import pytest
from docx import Document
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import mysql
from app.core.database import Base
from app.services.job_parser import detect_openings,public_addresses,structure_job_requirements
from app.services.matching_service import evaluate_matching
from app.models.domain import JobRequirement

PREFIX='/api/v1'
def create_job(c,**extra):
    body={'title':'Analista de testes','description':'Requisitos: Excel e atendimento. 1 vaga disponível.','openings':1,'internal':True,'published':True,'questions':['Qual sua disponibilidade?'],'requirements':[{'category':'mandatory','title':'Excel','weight':1}]}
    body.update(extra)
    r=c.post(PREFIX+'/jobs',json=body);assert r.status_code==200,r.text;return r.json()
def cv():
    d=Document();d.add_paragraph('Pessoa de Teste. Experiência com Excel e atendimento ao cliente. E-mail: teste@example.test. Telefone: (21) 99999-1234.');f=io.BytesIO();d.save(f);return f.getvalue()
def upload(c,job):
    r=c.post(f'{PREFIX}/jobs/{job}/resumes/upload',files={'files':('teste.docx',cv(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document')});assert r.status_code==200,r.text
    r=c.post(f'{PREFIX}/jobs/{job}/screenings',json={'local_only':True});assert r.status_code==200,r.text;return r.json()['results'][-1]
def conversation(c):
    j=create_job(c);r=upload(c,j['id']);response=c.post(f"{PREFIX}/jobs/{j['id']}/shortlist",json={'candidate_ids':[r['candidate_id']],'reviewed':True});assert response.status_code==200,response.text
    return c.get(PREFIX+'/conversations').json()[0]
def event(c,conversation,text,event_id):
    return c.post(PREFIX+'/webhooks/whatsapp',headers={'X-Webhook-Token':'test-webhook-secret'},json={'event_id':event_id,'conversation_id':conversation['id'],'phone':conversation['phone'],'text':text})

def test_private_routes_and_csrf(client):
    for route in ['/jobs','/talents','/conversations','/calendar/slots','/settings/integrations']:
        assert client.get(PREFIX+route).status_code==401
    assert client.get(PREFIX+'/public/jobs').status_code==200
    assert client.get('/static/../.env').status_code==404
    assert client.post(PREFIX+'/auth/login',json={'email':'rh@example.test','password':'wrong'}).status_code==401
    assert client.post(PREFIX+'/auth/login',json={'email':'rh@example.test','password':'test-password-123'}).status_code==200
    assert client.post(PREFIX+'/jobs',json={}).status_code==403

def test_no_automatic_demo_job(authenticated):
    assert authenticated.get(PREFIX+'/jobs').json()==[]

def test_analysis_saved_and_stale(authenticated):
    c=authenticated;j=create_job(c);r=upload(c,j['id']);assert r['score']==100
    report=c.get(f"{PREFIX}/jobs/{j['id']}/screenings").json();assert report['stale'] is False
    assert report['results'][0]['evidences']['source']=='local'
    j['requirements'][0]['title']='Python'
    assert c.put(f"{PREFIX}/jobs/{j['id']}",json=j).status_code==200
    assert c.get(f"{PREFIX}/jobs/{j['id']}/screenings").json()['stale'] is True
    assert c.post(f"{PREFIX}/jobs/{j['id']}/shortlist",json={'candidate_ids':[r['candidate_id']],'reviewed':True}).status_code==409

def test_shortlist_limit_and_idempotence(authenticated):
    c=authenticated;j=create_job(c);a=upload(c,j['id']);b=upload(c,j['id'])
    path=f"{PREFIX}/jobs/{j['id']}/shortlist"
    assert c.post(path,json={'candidate_ids':[a['candidate_id'],b['candidate_id']],'reviewed':True}).status_code==422
    assert c.post(path,json={'candidate_ids':[a['candidate_id']],'reviewed':True}).json()['queued']==1
    assert c.post(path,json={'candidate_ids':[a['candidate_id']],'reviewed':True}).json()['queued']==0
    assert c.post(path,json={'candidate_ids':[b['candidate_id']],'reviewed':True}).status_code==422
    msg=c.get(PREFIX+'/conversations').json()[0]['messages'][0]
    assert c.post(f"{PREFIX}/outbox/{msg['id']}/send").status_code==409
    assert c.get(PREFIX+'/conversations').json()[0]['messages'][0]['status']=='pending'

def test_webhook_triage_and_duplicates(authenticated):
    c=authenticated;conv=conversation(c)
    assert event(c,conv,'SIM','e1').json()['status']=='screening'
    assert event(c,conv,'SIM','e1').json()['duplicate'] is True
    assert event(c,conv,'Segunda-feira','e2').json()['status']=='completed'
    rows=c.get(PREFIX+'/conversations').json();assert len(rows[0]['answers'])==1
    assert rows[0]['answers'][0]['question']=='Qual sua disponibilidade?'
    assert event(c,conv,'SAIR','e3').json()['status']=='opted_out'
    assert all(m['status']=='cancelled' for m in c.get(PREFIX+'/conversations').json()[0]['messages'])

def test_slot_conflict_and_booking(authenticated):
    c=authenticated;conv=conversation(c);event(c,conv,'SIM','a1');event(c,conv,'Amanhã','a2')
    start=datetime.now(timezone.utc)+timedelta(days=1)
    body={'recruiter':'rh@example.test','starts_at':start.isoformat(),'ends_at':(start+timedelta(minutes=30)).isoformat(),'location':'Unidade DDM'}
    r=c.post(PREFIX+'/calendar/slots',json=body);assert r.status_code==200,r.text
    assert c.post(PREFIX+'/calendar/slots',json=body).status_code==409
    path=f"{PREFIX}/calendar/slots/{r.json()['id']}/book"
    assert c.post(path,json={'conversation_id':conv['id']}).status_code==200
    assert c.post(path,json={'conversation_id':conv['id']}).status_code==422

def test_internal_application_update_and_privacy(authenticated):
    c=authenticated;j=create_job(c)
    data={'name':'Pessoa Interna','email':'interno@example.test','phone':'21999991234','employee_id':'TEST-1','department':'Operações','current_role':'Assistente','consent':'true','job_id':str(j['id'])}
    def apply(): return c.post(PREFIX+'/public/apply',data=data,files={'file':('cv.docx',cv())})
    r=apply();assert r.status_code==200,r.text
    data['update_token']=r.json()['update_token'];data['name']='Nome atualizado'
    assert apply().status_code==200
    talents=c.get(PREFIX+'/talents').json();assert len(talents)==1;assert talents[0]['name']=='Nome atualizado';assert len(talents[0]['applications'])==1
    assert c.get(f"{PREFIX}/talents/{talents[0]['id']}/resume").status_code==200
    assert 'email' not in c.get(PREFIX+'/public/jobs').json()[0]
    data['update_token']='bad';assert apply().status_code==403

def test_invalid_upload_and_no_text(authenticated):
    c=authenticated;j=create_job(c)
    path=f"{PREFIX}/jobs/{j['id']}/resumes/upload"
    assert c.post(path,files={'files':('../../bad.exe',b'bad')}).status_code==422
    assert c.post(path,files={'files':('../../bad.pdf',b'bad')}).status_code==422

def test_extraction_never_invents_openings():
    assert detect_openings('Quantidade de vagas: 3')==3
    assert detect_openings('Venha trabalhar conosco!') is None
    assert detect_openings('3 vagas e 4 vagas') is None
    assert structure_job_requirements('Vaga: Analista')==[]

@pytest.mark.parametrize('url',['http://example.com','https://127.0.0.1','https://[::1]','https://user:pass@example.com','https://localhost'])
def test_ssrf_rejected(url):
    with pytest.raises(ValueError): public_addresses(url)

def test_no_fabricated_experience_or_partial_domain_match():
    requirements=[JobRequirement(category='mandatory',title='Excel avançado',weight=1)]
    result=evaluate_matching('12 meses de experiência com atendimento. Sem Excel avançado.','Teste',requirements)
    assert result['score']==0;assert result['experience'].startswith('1 ano')
    assert evaluate_matching('Atendimento ao cliente.','Teste',requirements)['experience']=='Tempo não evidenciado'

def test_mysql_schema_compiles():
    for table in Base.metadata.sorted_tables: assert str(CreateTable(table).compile(dialect=mysql.dialect()))

def test_delivery_claim_prevents_resending(authenticated,monkeypatch):
    from app.services.whatsapp_service import whatsapp_service
    c=authenticated;conv=conversation(c);message_id=conv['messages'][0]['id']
    sent=[]
    monkeypatch.setattr(whatsapp_service,'configured',lambda:True)
    monkeypatch.setattr(whatsapp_service,'send',lambda *args:sent.append(args) or 'provider-1')
    path=f'{PREFIX}/outbox/{message_id}/send'
    assert c.post(path).json()['status']=='accepted'
    assert c.post(path).status_code==409
    assert len(sent)==1

def test_uncertain_delivery_is_not_retried(authenticated,monkeypatch):
    from app.services.whatsapp_service import whatsapp_service
    c=authenticated;conv=conversation(c);message_id=conv['messages'][0]['id']
    monkeypatch.setattr(whatsapp_service,'configured',lambda:True)
    def fail(*args): raise TimeoutError()
    monkeypatch.setattr(whatsapp_service,'send',fail)
    path=f'{PREFIX}/outbox/{message_id}/send'
    assert c.post(path).json()['status']=='uncertain'
    assert c.post(path).status_code==409

def test_local_parser_does_not_turn_intro_into_requirement():
    assert structure_job_requirements('Venha fazer parte da nossa equipe.\nObrigatório: Excel')==[{'category':'mandatory','title':'Excel','weight':1}]
