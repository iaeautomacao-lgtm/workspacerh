from tests.test_workflow import PREFIX, create_job, upload, conversation

def test_delete_requires_csrf_header_and_login(client):
    # Sem o cabecalho proprio da aplicacao, a protecao CSRF barra antes de olhar a sessao.
    assert client.delete(PREFIX + '/jobs/1').status_code == 403
    assert client.delete(PREFIX + '/jobs/1/resumes/1').status_code == 403
    # Com o cabecalho e sem sessao, barra por autenticacao.
    headers = {'X-Requested-With': 'DDM-RH'}
    assert client.delete(PREFIX + '/jobs/1', headers=headers).status_code == 401
    assert client.delete(PREFIX + '/jobs/1/resumes/1', headers=headers).status_code == 401

def test_delete_job_removes_resumes_and_file(authenticated):
    from pathlib import Path
    from app.core.database import get_db
    from app.main import app
    from app.models.domain import Resume, Job
    c = authenticated
    job = create_job(c)
    row = upload(c, job['id'])
    with next(app.dependency_overrides[get_db]()) as db:
        path = Path(db.get(Resume, row['id']).file_path)
    assert path.is_file()

    response = c.delete(f"{PREFIX}/jobs/{job['id']}")
    assert response.status_code == 200, response.text
    assert response.json() == {'deleted': True, 'resumes_removed': 1, 'candidates_removed': 1}

    assert c.get(PREFIX + '/jobs').json() == []
    assert not path.is_file(), 'o arquivo do curriculo deve sair do disco'
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.get(Job, job['id']) is None
        assert db.get(Resume, row['id']) is None

def test_delete_job_is_blocked_by_candidate_contact(authenticated):
    c = authenticated
    conv = conversation(c)
    job_id = c.get(PREFIX + '/jobs').json()[0]['id']
    response = c.delete(f'{PREFIX}/jobs/{job_id}')
    assert response.status_code == 409
    assert 'conversa' in response.json()['detail']
    # A vaga continua inteira.
    assert [j['id'] for j in c.get(PREFIX + '/jobs').json()] == [job_id]

def test_delete_resume_drops_the_orphan_candidate(authenticated):
    from app.core.database import get_db
    from app.main import app
    from app.models.domain import Candidate, Resume
    c = authenticated
    job = create_job(c)
    row = upload(c, job['id'])
    response = c.delete(f"{PREFIX}/jobs/{job['id']}/resumes/{row['id']}")
    assert response.status_code == 200, response.text
    assert response.json() == {'deleted': True, 'candidate_removed': True}
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.get(Resume, row['id']) is None
        assert db.get(Candidate, row['candidate_id']) is None
    # A vaga permanece.
    assert len(c.get(PREFIX + '/jobs').json()) == 1

def test_resume_of_another_job_is_not_deleted(authenticated):
    c = authenticated
    first = create_job(c)
    second = create_job(c)
    row = upload(c, first['id'])
    assert c.delete(f"{PREFIX}/jobs/{second['id']}/resumes/{row['id']}").status_code == 404

def test_deletion_is_audited(authenticated):
    from app.core.database import get_db
    from app.main import app
    from app.models.domain import AuditLog
    c = authenticated
    job = create_job(c)
    upload(c, job['id'])
    c.delete(f"{PREFIX}/jobs/{job['id']}")
    with next(app.dependency_overrides[get_db]()) as db:
        actions = [a.action for a in db.query(AuditLog).all()]
    assert 'job_deleted' in actions

def test_deleting_a_job_does_not_leave_orphan_candidates(authenticated):
    from app.core.database import get_db
    from app.main import app
    from app.models.domain import Candidate
    c = authenticated
    job = create_job(c)
    row = upload(c, job['id'])
    c.delete(f"{PREFIX}/jobs/{job['id']}")
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.get(Candidate, row['candidate_id']) is None
        assert db.query(Candidate).count() == 0

def test_candidate_with_contact_survives_the_job_deletion(authenticated):
    from app.core.database import get_db
    from app.main import app
    from app.models.domain import Candidate
    from app.models.exam import Exam, ExamAttempt
    from app.core.time import utcnow
    from datetime import timedelta
    c = authenticated
    job = create_job(c)
    row = upload(c, job['id'])
    # Prova aplicada em outra vaga preserva o cadastro do candidato.
    with next(app.dependency_overrides[get_db]()) as db:
        exam = Exam(title='Prova', duration_minutes=30, open=False); db.add(exam); db.flush()
        db.add(ExamAttempt(exam_id=exam.id, candidate_id=row['candidate_id'], token_hash='x' * 64,
                           name='Pessoa', expires_at=utcnow() + timedelta(hours=1)))
        db.commit()
    assert c.delete(f"{PREFIX}/jobs/{job['id']}").json()['candidates_removed'] == 0
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.get(Candidate, row['candidate_id']) is not None
