import pytest
from app.services import question_bank as bank
from tests.test_exams import sit
from tests.test_workflow import PREFIX

def test_every_question_in_the_bank_is_well_formed():
    """Uma questão com gabarito errado é pior que nenhuma questão."""
    for row in bank.BANK:
        rotulo = row['statement'][:60]
        assert row['subject'] in bank.SUBJECTS, rotulo
        assert row['level'] in bank.LEVELS, rotulo
        assert row['weight'] > 0, rotulo
        if row['kind'] == 'choice':
            options = row['options']
            assert isinstance(options, list) and 2 <= len(options) <= 10, rotulo
            assert all(str(o).strip() for o in options), rotulo
            assert isinstance(row['answer_key'], int) and not isinstance(row['answer_key'], bool), rotulo
            assert 0 <= row['answer_key'] < len(options), rotulo
            assert len(set(options)) == len(options), f'alternativa repetida: {rotulo}'
        elif row['kind'] == 'truefalse':
            assert isinstance(row['answer_key'], bool), rotulo
        elif row['kind'] == 'matching':
            left, right = row['options']['left'], row['options']['right']
            assert 2 <= len(left) <= 10 and 2 <= len(right) <= 10, rotulo
            assert len(row['answer_key']) == len(left), rotulo
            assert all(0 <= i < len(right) for i in row['answer_key']), rotulo
            assert len(set(row['answer_key'])) == len(row['answer_key']), f'associacao ambigua: {rotulo}'
        elif row['kind'] == 'essay':
            assert row['rubric'], rotulo
            assert all(c['max'] > 0 and c['name'].strip() for c in row['rubric']), rotulo
        else:
            pytest.fail(f'tipo desconhecido em {rotulo}')

def test_every_template_produces_a_usable_exam():
    for key, modelo in bank.TEMPLATES.items():
        rows = bank.assemble(modelo['mix'], modelo['level'])
        assert rows, key
        assert len({id(r) for r in rows}) == len(rows), f'{key} repetiu questao'
        assert modelo['duration_minutes'] >= 5

def test_level_includes_the_levels_below():
    junior = bank.pool('dp', 'junior')
    pleno = bank.pool('dp', 'pleno')
    assert len(pleno) > len(junior)
    assert all(q in pleno for q in junior)

def test_library_endpoint(authenticated):
    data = authenticated.get(PREFIX + '/exam-library').json()
    assert {s['key'] for s in data['subjects']} == set(bank.SUBJECTS)
    assert len(data['templates']) == len(bank.TEMPLATES)
    assert all(t['questions'] > 0 for t in data['templates'])

def test_build_from_template(authenticated):
    c = authenticated
    response = c.post(PREFIX + '/exams/build', json={'title': 'Prova de DP', 'template': 'dp-pleno', 'duration_minutes': 90})
    assert response.status_code == 200, response.text
    exam = response.json()
    assert exam['questions_count'] > 5
    assert exam['level'] == 'pleno'
    detail = c.get(f"{PREFIX}/exams/{exam['id']}").json()
    # O gabarito chega pronto para o RH revisar.
    escolha = [q for q in detail['questions'] if q['kind'] == 'choice'][0]
    assert isinstance(escolha['answer_key'], int)

def test_build_by_subject_mix(authenticated):
    c = authenticated
    response = c.post(PREFIX + '/exams/build', json={
        'title': 'Triagem', 'level': 'junior', 'duration_minutes': 40,
        'mix': [{'subject': 'portugues', 'amount': 3}, {'subject': 'logica', 'amount': 2}]})
    assert response.status_code == 200, response.text
    assert response.json()['questions_count'] == 5

def test_build_rejects_empty_or_unknown_selection(authenticated):
    c = authenticated
    assert c.post(PREFIX + '/exams/build', json={'title': 'Vazia', 'mix': []}).status_code == 422
    assert c.post(PREFIX + '/exams/build', json={'title': 'Materia invalida', 'mix': [{'subject': 'astrologia', 'amount': 2}]}).status_code == 422
    assert c.post(PREFIX + '/exams/build', json={'title': 'Modelo invalido', 'template': 'nao-existe'}).status_code == 404

def test_access_code_protects_the_online_exam(authenticated):
    c = authenticated
    exam = c.post(PREFIX + '/exams/build', json={'title': 'Online', 'template': 'triagem-geral', 'mode': 'online', 'access_code': 'DDM2026'}).json()
    c.post(f"{PREFIX}/exams/{exam['id']}/open", json={'open': True})
    listado = c.get(PREFIX + '/public/exams').json()[0]
    assert listado['requires_code'] is True
    assert 'access_code' not in listado, 'o codigo nao pode vazar para o candidato'
    corpo = {'name': 'Pessoa de Teste', 'email': 'a@b.test', 'phone': '21999991234', 'consent': True}
    assert c.post(f"{PREFIX}/public/exams/{exam['id']}/start", json=corpo).status_code == 403
    assert c.post(f"{PREFIX}/public/exams/{exam['id']}/start", json={**corpo, 'access_code': 'errado'}).status_code == 403
    assert c.post(f"{PREFIX}/public/exams/{exam['id']}/start", json={**corpo, 'access_code': 'DDM2026'}).status_code == 200

def test_exam_without_code_stays_open(authenticated):
    c = authenticated
    exam = c.post(PREFIX + '/exams/build', json={'title': 'Sem codigo', 'template': 'triagem-geral'}).json()
    c.post(f"{PREFIX}/exams/{exam['id']}/open", json={'open': True})
    assert c.get(PREFIX + '/public/exams').json()[0]['requires_code'] is False
    assert sit(c, exam['id'])['attempt_id']

def test_template_keeps_its_own_duration_unless_overridden(authenticated):
    c = authenticated
    padrao = c.post(PREFIX + '/exams/build', json={'title': 'Com duracao do modelo', 'template': 'dp-pleno'}).json()
    assert padrao['duration_minutes'] == bank.TEMPLATES['dp-pleno']['duration_minutes']
    custom = c.post(PREFIX + '/exams/build', json={'title': 'Com duracao propria', 'template': 'dp-pleno', 'duration_minutes': 120}).json()
    assert custom['duration_minutes'] == 120
