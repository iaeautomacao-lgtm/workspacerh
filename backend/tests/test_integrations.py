import json
import pytest
from app.models.domain import JobRequirement
from app.services import llm_service,calendar_service

class FakeResponse:
    def __init__(self,data): self.data=json.dumps(data).encode()
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,*args): return self.data

def test_ai_quote_validation_and_server_scoring(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test')
    monkeypatch.setattr(llm_service,'structured_call',lambda *a: {'evaluations':[{'index':0,'status':'Atende','quote':'Experiência com Python','detail':'irrelevant'}],'experience':'Não evidenciado','summary':'Revisar'})
    result=llm_service.evaluate_with_ai('Vaga','Descrição','Experiência somente com Excel.','Pessoa',[JobRequirement(category='mandatory',title='Python',weight=1)])
    assert result['score']==0
    assert result['evidences']['all'][0]['status']=='Não evidenciado'

def test_ai_incomplete_requirements_rejected(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test')
    monkeypatch.setattr(llm_service,'structured_call',lambda *a: {'evaluations':[],'experience':'','summary':''})
    with pytest.raises(llm_service.AIUnavailable):
        llm_service.evaluate_with_ai('Vaga','Descrição','Excel','Pessoa',[JobRequirement(category='mandatory',title='Excel',weight=1)])

def configure_outlook(monkeypatch):
    for key,value in {'MS_TENANT_ID':'test-tenant','MS_CLIENT_ID':'test-client','MS_CLIENT_SECRET':'test-secret','MS_RH_MAILBOX':'rh@example.test','MS_ALLOWED_MAILBOXES':'rh@example.test'}.items(): monkeypatch.setenv(key,value)
    monkeypatch.setattr(calendar_service,'token',lambda:'test-token')

@pytest.mark.parametrize('items,view,available',[([], '0000',True),([{'status':'busy'}],'2222',False),([{'status':'tentative'}],'1111',False)])
def test_outlook_availability(monkeypatch,items,view,available):
    from datetime import datetime,timedelta
    configure_outlook(monkeypatch)
    monkeypatch.setattr(calendar_service.urllib.request,'urlopen',lambda *a,**k:FakeResponse({'value':[{'scheduleItems':items,'availabilityView':view}]}))
    start=datetime(2027,1,1,12)
    if available: assert calendar_service.ensure_available('rh@example.test',start,start+timedelta(minutes=30))=='outlook'
    else:
        with pytest.raises(calendar_service.CalendarUnavailable): calendar_service.ensure_available('rh@example.test',start,start+timedelta(minutes=30))

def test_outlook_failure_never_means_available(monkeypatch):
    from datetime import datetime,timedelta
    configure_outlook(monkeypatch)
    def fail(*a,**k): raise OSError('network failure')
    monkeypatch.setattr(calendar_service.urllib.request,'urlopen',fail)
    with pytest.raises(calendar_service.CalendarUnavailable): calendar_service.ensure_available('rh@example.test',datetime(2027,1,1),datetime(2027,1,2))

def test_quote_verification_tolerates_model_formatting():
    from app.services.llm_service import verified_quote
    resume = 'Curso Excel Intermediario - 2025. Atuacao em folha de pagamento.'
    # O modelo costuma devolver a citacao entre aspas ou com espacos extras.
    assert verified_quote('"Curso Excel Intermediario - 2025"', resume) == 'Curso Excel Intermediario - 2025'
    assert verified_quote('\u201cfolha de pagamento\u201d', resume) == 'folha de pagamento'
    assert verified_quote('  Curso   Excel   Intermediario  ', resume)
    # A exigencia de trecho literal continua valendo.
    assert verified_quote('', resume) is None
    assert verified_quote('   ', resume) is None
    assert verified_quote('Ingles fluente', resume) is None
