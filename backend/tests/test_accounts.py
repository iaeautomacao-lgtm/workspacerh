from tests.test_workflow import PREFIX

NOVA = {'name': 'Analista de RH', 'email': 'analista@example.test', 'password': 'senha-bem-longa-123', 'role': 'rh'}

def promote(client, email='rh@example.test'):
    """A conta da fixture nasce como 'rh'; o sistema promove a mais antiga a administrador."""
    from app.core.database import get_db
    from app.main import app
    from app.models.workflow import Account
    with next(app.dependency_overrides[get_db]()) as db:
        conta = db.query(Account).filter_by(email=email).first()
        conta.role = 'admin'
        db.commit()
        return conta.id

def test_account_routes_are_private(client):
    assert client.get(PREFIX + '/accounts').status_code == 401

def test_only_admin_manages_accounts(authenticated):
    c = authenticated
    # Sem promover, a conta e 'rh' e nao gerencia acessos.
    assert c.get(PREFIX + '/accounts').status_code == 403
    assert c.post(PREFIX + '/accounts', json=NOVA).status_code == 403
    promote(c)
    assert c.get(PREFIX + '/accounts').status_code == 200

def test_create_list_and_login_with_the_new_account(authenticated):
    c = authenticated
    promote(c)
    response = c.post(PREFIX + '/accounts', json=NOVA)
    assert response.status_code == 200, response.text
    assert response.json()['role'] == 'rh'
    assert 'password' not in response.json() and 'password_hash' not in response.json()
    assert len(c.get(PREFIX + '/accounts').json()) == 2
    # A conta nova entra no sistema.
    assert c.post(PREFIX + '/auth/login', json={'email': NOVA['email'], 'password': NOVA['password']}).status_code == 200

def test_duplicate_email_and_weak_password_are_refused(authenticated):
    c = authenticated
    promote(c)
    c.post(PREFIX + '/accounts', json=NOVA)
    assert c.post(PREFIX + '/accounts', json=NOVA).status_code == 409
    assert c.post(PREFIX + '/accounts', json={**NOVA, 'email': 'outro@example.test', 'password': 'curta'}).status_code == 422

def test_deactivating_blocks_the_login_and_the_open_session(authenticated):
    c = authenticated
    admin_id = promote(c)
    nova = c.post(PREFIX + '/accounts', json=NOVA).json()
    resposta = c.put(f"{PREFIX}/accounts/{nova['id']}", json={'name': NOVA['name'], 'role': 'rh', 'active': False})
    assert resposta.status_code == 200
    assert resposta.json()['active'] is False
    assert c.post(PREFIX + '/auth/login', json={'email': NOVA['email'], 'password': NOVA['password']}).status_code == 403

def test_password_reset_by_admin(authenticated):
    c = authenticated
    promote(c)
    nova = c.post(PREFIX + '/accounts', json=NOVA).json()
    assert c.post(f"{PREFIX}/accounts/{nova['id']}/password", json={'new_password': 'outra-senha-longa-9'}).status_code == 200
    assert c.post(PREFIX + '/auth/login', json={'email': NOVA['email'], 'password': NOVA['password']}).status_code == 401
    assert c.post(PREFIX + '/auth/login', json={'email': NOVA['email'], 'password': 'outra-senha-longa-9'}).status_code == 200

def test_change_own_password_requires_the_current_one(authenticated):
    c = authenticated
    assert c.post(PREFIX + '/auth/password', json={'current_password': 'errada', 'new_password': 'nova-senha-longa-1'}).status_code == 403
    resposta = c.post(PREFIX + '/auth/password', json={'current_password': 'test-password-123', 'new_password': 'nova-senha-longa-1'})
    assert resposta.status_code == 200, resposta.text
    # A sessao atual continua valida; a senha antiga nao serve mais.
    assert c.get(PREFIX + '/auth/me').status_code == 200
    assert c.post(PREFIX + '/auth/login', json={'email': 'rh@example.test', 'password': 'test-password-123'}).status_code == 401

def test_the_last_admin_cannot_be_removed_or_demoted(authenticated):
    c = authenticated
    admin_id = promote(c)
    assert c.delete(f'{PREFIX}/accounts/{admin_id}').status_code == 422
    resposta = c.put(f'{PREFIX}/accounts/{admin_id}', json={'name': 'RH Teste', 'role': 'rh', 'active': True})
    assert resposta.status_code == 422
    assert 'administrador' in resposta.json()['detail']
    # Com outro administrador ativo, a troca passa.
    outro = c.post(PREFIX + '/accounts', json={**NOVA, 'role': 'admin'}).json()
    assert c.put(f'{PREFIX}/accounts/{admin_id}', json={'name': 'RH Teste', 'role': 'rh', 'active': True}).status_code == 200

def test_delete_account_and_audit(authenticated):
    from app.core.database import get_db
    from app.main import app
    from app.models.domain import AuditLog
    c = authenticated
    promote(c)
    nova = c.post(PREFIX + '/accounts', json=NOVA).json()
    assert c.delete(f"{PREFIX}/accounts/{nova['id']}").status_code == 200
    assert len(c.get(PREFIX + '/accounts').json()) == 1
    with next(app.dependency_overrides[get_db]()) as db:
        acoes = {a.action for a in db.query(AuditLog).all()}
    assert {'account_created', 'account_deleted'} <= acoes
