from fastapi.testclient import TestClient
import pytest
from jarvis.api import create_app
from jarvis.storage import Store

@pytest.fixture
def api():
    s = Store(':memory:')
    c = TestClient(create_app(s, 'x' * 32))
    yield c
    s.close()

def test_http_authentication_and_output(api):
    assert api.get('/health').status_code == 200
    assert api.post('/v1/tasks', json={'objective':'test'}).status_code == 401
    h = {'Authorization':'Bearer ' + 'x' * 32}
    create = api.post('/v1/tasks', json={'objective':'test'},headers=h)
    assert create.status_code == 200
    taskid = create.json()['id']
    assert api.get('/v1/tasks/'+taskid,headers=h).json()['status'] == 'READY'
    run = api.post('/v1/tasks/'+taskid+'/run-echo',headers=h,json={})
    assert run.status_code == 200 and run.json()['output'] == 'test'
    assert api.post('/v1/tasks/'+taskid+'/run-echo',headers=h,json={}).status_code == 409

def test_api_cannot_grant_high_risk_approval(api):
    h = {'Authorization':'Bearer ' + 'x' * 32}
    create = api.post('/v1/tasks', json={'objective':'sensitive','risk':'HIGH'},headers=h)
    taskid = create.json()['id']
    approval = api.post('/v1/tasks/'+taskid+'/approval-request',headers=h)
    aid = approval.json()['approval_id']
    assert api.post('/v1/tasks/'+taskid+'/run-echo',headers=h,json={'approval_id':aid}).status_code == 403
    assert api.post('/v1/approve-grant',headers=h,json={'approval_id':aid}).status_code == 404

def test_invalid_requests_rejected(api):
    h = {'Authorization':'Bearer ' + 'x' * 32}
    assert api.post('/v1/tasks', json={'objective':''},headers=h).status_code == 422
    assert api.post('/v1/tasks', json={'objective':'x','capability':'exec.shell'},headers=h).status_code == 403
