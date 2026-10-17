"""API-level proof that an n8n caller cannot turn its credential into general operator authority."""
import pytest
from fastapi.testclient import TestClient

from jarvis.api import create_app
from jarvis.storage import Store


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv('JARVIS_N8N_INGEST_TOKEN', 'n' * 48)
    monkeypatch.setenv('JARVIS_N8N_WORKFLOW_IDS', 'workflow_1,workflow_2')
    store = Store(':memory:')
    client = TestClient(create_app(store, secret='o' * 48))
    yield client, store
    store.close()


def payload(execution='run-1', workflow='workflow_1', objective='local echo only'):
    return {'workflow_id': workflow, 'execution_id': execution, 'objective': objective}


def test_allowlisted_n8n_request_reaches_evidence_gated_core(setup):
    client, store = setup
    r = client.post('/v1/integrations/n8n/echo', json=payload(),
                    headers={'X-Jarvis-N8n-Token': 'n' * 48})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['status'] == 'COMPLETED'
    assert body['result'] == 'local echo only'
    assert body['verified'] is True
    t = store.get(body['task_id'])
    assert t['category'] == 'analysis' and t['capability'] == 'model.text' and t['risk'] == 'LOW'
    assert len([e for e in store.history(t['id']) if e['kind'] == 'action.finalized']) == 1


def test_duplicate_delivery_is_idempotent_and_different_body_conflicts(setup):
    client, store = setup
    h = {'X-Jarvis-N8n-Token': 'n' * 48}
    first = client.post('/v1/integrations/n8n/echo', json=payload(), headers=h)
    second = client.post('/v1/integrations/n8n/echo', json=payload(), headers=h)
    assert first.status_code == second.status_code == 200
    assert first.json()['task_id'] == second.json()['task_id']
    different = client.post('/v1/integrations/n8n/echo',
                            json=payload(objective='changed request'), headers=h)
    assert different.status_code == 409
    assert store.db.execute('SELECT COUNT(*) FROM actions').fetchone()[0] == 1


def test_n8n_token_is_not_operator_token(setup):
    client, _ = setup
    h = {'X-Jarvis-N8n-Token': 'n' * 48}
    assert client.post('/v1/tasks', json={'objective':'escalate'}, headers=h).status_code == 401
    assert client.post('/v1/integrations/n8n/echo', json=payload(),
                       headers={'X-Jarvis-N8n-Token':'o' * 48}).status_code == 401


def test_bad_workflow_and_extra_fields_are_denied(setup):
    client, store = setup
    h = {'X-Jarvis-N8n-Token':'n' * 48}
    assert client.post('/v1/integrations/n8n/echo',
                       json=payload(workflow='not-allowed'), headers=h).status_code == 403
    assert client.post('/v1/integrations/n8n/echo',
                       json={**payload(), 'risk': 'CRITICAL'}, headers=h).status_code == 422
    assert client.post('/v1/integrations/n8n/echo',
                       json={**payload(), 'tool': 'exec.shell'}, headers=h).status_code == 422
    assert store.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 0


def test_endpoint_is_disabled_when_secret_or_allowlist_missing(monkeypatch):
    monkeypatch.delenv('JARVIS_N8N_INGEST_TOKEN', raising=False)
    monkeypatch.delenv('JARVIS_N8N_WORKFLOW_IDS', raising=False)
    store = Store(':memory:')
    try:
        client = TestClient(create_app(store, secret='o' * 48))
        resp = client.post('/v1/integrations/n8n/echo', json=payload(),
                           headers={'X-Jarvis-N8n-Token': 'n' * 48})
        assert resp.status_code == 401
    finally:
        store.close()


def test_execution_identity_is_validated_and_bounded(setup):
    client, _ = setup
    h = {'X-Jarvis-N8n-Token': 'n' * 48}
    assert client.post('/v1/integrations/n8n/echo',
                       json=payload(execution='x' * 120), headers=h).status_code == 422
    assert client.post('/v1/integrations/n8n/echo',
                       json=payload(objective='x' * 2500), headers=h).status_code == 422

def test_integration_secret_cannot_equal_operator_secret(monkeypatch):
    monkeypatch.setenv('JARVIS_N8N_INGEST_TOKEN', 'o' * 48)
    store = Store(':memory:')
    try:
        client = TestClient(create_app(store, secret='o' * 48))
        response = client.post('/v1/integrations/n8n/echo', json=payload(),
                               headers={'X-Jarvis-N8n-Token': 'o' * 48})
        assert response.status_code == 401
    finally:
        store.close()


def test_parallel_duplicate_delivery_never_duplicates_action(setup):
    from concurrent.futures import ThreadPoolExecutor
    client, store = setup
    headers = {'X-Jarvis-N8n-Token': 'n' * 48}

    def deliver(_):
        return client.post('/v1/integrations/n8n/echo', json=payload(), headers=headers)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(deliver, range(16)))
    assert all(response.status_code in (200, 202) for response in results)
    assert len({response.json()['task_id'] for response in results}) == 1
    assert store.db.execute('SELECT COUNT(*) FROM actions').fetchone()[0] == 1
    assert store.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 1


def test_repeated_delivery_survives_sqlite_restart(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_N8N_INGEST_TOKEN', 'n' * 48)
    monkeypatch.setenv('JARVIS_N8N_WORKFLOW_IDS', 'workflow_1')
    path = str(tmp_path / 'persist.db')
    first_db = Store(path)
    try:
        first = TestClient(create_app(first_db, secret='o' * 48))
        result = first.post('/v1/integrations/n8n/echo', json=payload(),
                            headers={'X-Jarvis-N8n-Token': 'n' * 48})
        assert result.status_code == 200
        task_id = result.json()['task_id']
    finally:
        first_db.close()
    second_db = Store(path)
    try:
        second = TestClient(create_app(second_db, secret='o' * 48))
        again = second.post('/v1/integrations/n8n/echo', json=payload(),
                            headers={'X-Jarvis-N8n-Token': 'n' * 48})
        assert again.status_code == 200
        assert again.json()['task_id'] == task_id
        assert second_db.db.execute('SELECT COUNT(*) FROM actions').fetchone()[0] == 1
    finally:
        second_db.close()
