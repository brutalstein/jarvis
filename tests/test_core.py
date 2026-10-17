from concurrent.futures import ThreadPoolExecutor
import time
import pytest

from jarvis.contracts import Action, Capability, Conflict, Denied, Risk, State, TaskSpec
from jarvis.engine import Engine
from jarvis.policy import Principal
from jarvis.routing import RouteRequest, Router
from jarvis.storage import Store

@pytest.fixture
def setup(tmp_path):
    db = Store(str(tmp_path / 'store.db'))
    yield Engine(db)
    db.close()

OP = Principal('operator', frozenset({'model.text'}))
NO = Principal('attacker', frozenset())

def test_happy_path_and_evidence(setup):
    t = setup.admit(TaskSpec('Hello'))
    assert t['status'] == State.READY
    r = setup.run_echo(t['id'], OP)
    assert r.output == 'Hello'
    assert r.evidence['passed'] is True
    assert setup.store.get(t['id'])['status'] == State.COMPLETED
    assert any(e['kind'] == 'action.finalized' for e in setup.store.history(t['id']))

def test_unverified_cannot_complete(setup):
    t = setup.admit(TaskSpec('x'))
    setup.store.transition(t['id'], State.RUNNING)
    setup.store.transition(t['id'], State.VERIFYING)
    with pytest.raises(Denied):
        setup.store.transition(t['id'], State.COMPLETED, {'verified':False, 'evidence': {'ok': True}})

def test_terminal_cannot_reverse(setup):
    t = setup.admit(TaskSpec('x'))
    setup.cancel(t['id'])
    with pytest.raises(Conflict):
        setup.store.transition(t['id'], State.READY)

def test_no_unauthorized_execution(setup):
    t = setup.admit(TaskSpec('x'))
    with pytest.raises(Denied):
        setup.run_echo(t['id'], NO)
    assert setup.store.get(t['id'])['status'] == State.READY

def test_strict_risk_and_exact_action_approval(setup):
    t = setup.admit(TaskSpec('security task', risk=Risk.HIGH))
    assert t['status'] == State.WAITING_FOR_APPROVAL
    with pytest.raises(Denied):
        setup.run_echo(t['id'], OP)
    a = setup.request_approval(t['id'], OP)
    # Proposal is not automatically human approval.
    with pytest.raises(Denied):
        setup.run_echo(t['id'], OP, approval_id=a)
    with pytest.raises(Denied):
        setup.gate.grant_approval(a, human_confirmation='incorrect')
    setup.gate.grant_approval(a, human_confirmation=a)
    action = setup.propose_echo(t['id'])
    changed = Action(action.task_id, action.kind, action.target, {'text':'malicious'}, action.capability, action.risk, action.key)
    with pytest.raises(Denied):
        setup.gate.authorize(changed, OP, approval_id=a)
    setup.run_echo(t['id'], OP, approval_id=a)
    assert setup.store.get(t['id'])['status'] == State.COMPLETED

def test_approval_single_use(setup):
    t = setup.admit(TaskSpec('x', risk=Risk.HIGH))
    a = setup.request_approval(t['id'], OP)
    setup.gate.grant_approval(a, human_confirmation=a)
    action = setup.propose_echo(t['id'])
    setup.gate.authorize(action, OP, a)
    with pytest.raises(Conflict):
        setup.gate.authorize(action, OP, a)

def test_idempotency_key_collision(setup):
    a = setup.admit(TaskSpec('alpha', idempotency_key='same'))
    b = setup.admit(TaskSpec('alpha', idempotency_key='same'))
    assert a['id'] == b['id']
    with pytest.raises(Conflict):
        setup.admit(TaskSpec('beta', idempotency_key='same'))

def test_dependency_wait_and_resume(setup):
    parent = setup.admit(TaskSpec('parent'))
    child = setup.admit(TaskSpec('child', dependencies=(parent['id'],)))
    assert child['status'] == State.WAITING_FOR_DEPENDENCY
    with pytest.raises(Denied):
        setup.resume_dependencies(child['id'])
    setup.run_echo(parent['id'], OP)
    assert setup.resume_dependencies(child['id'])['status'] == State.READY
    setup.run_echo(child['id'], OP)

def test_unknown_dependency_and_duplicates_fail(setup):
    with pytest.raises(Denied):
        setup.admit(TaskSpec('x', dependencies=('missing',)))
    with pytest.raises(Denied):
        setup.admit(TaskSpec('x', dependencies=('same','same')))

def test_lease_exclusion(setup):
    t = setup.admit(TaskSpec('x'))
    results = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda i: setup.store.lease(t['id'], f'worker{i}', time.time()), range(12)))
    assert results.count(True) == 1

def test_recovery_survives_restart(tmp_path):
    path = str(tmp_path / 'durable.db')
    one = Store(path)
    t = Engine(one).admit(TaskSpec('x'))
    one.transition(t['id'], State.RUNNING)
    one.close()
    two = Store(path)
    assert two.reconcile_interrupted() == [t['id']]
    assert two.get(t['id'])['status'] == State.RECOVERY_REQUIRED
    assert two.reconcile_interrupted() == []
    two.close()

def test_router_deterministic_and_fail_closed():
    r = Router([Capability('gemini',frozenset({'analysis'}),True,0,2), Capability('claude',frozenset({'analysis'}),True,0,1)])
    req = RouteRequest('analysis','model.text',frozenset({'gemini','claude'}))
    assert r.choose(req).provider == 'claude'
    with pytest.raises(Denied):
        r.choose(RouteRequest('coding','model.text',frozenset({'gemini','claude'})))

def test_no_action_replay(setup):
    t = setup.admit(TaskSpec('hello'))
    setup.run_echo(t['id'], OP)
    with pytest.raises(Conflict):
        setup.run_echo(t['id'], OP)

def test_security_config_rejects_external_urls():
    from jarvis.adapters import N8N, OpenClaw
    with pytest.raises(Denied):
        N8N('http://evil.example', 'token')
    with pytest.raises(Denied):
        OpenClaw('ws://evil.example:18789', 'token')

def test_risk_action_digest_changes_with_parameters(setup):
    t = setup.admit(TaskSpec('x'))
    a = setup.propose_echo(t['id'])
    b = Action(a.task_id,a.kind,a.target,{'text':'other'},a.capability,a.risk,a.key)
    assert a.digest() != b.digest()

def test_request_validation(setup):
    with pytest.raises(Denied):
        setup.admit(TaskSpec(' '))
    with pytest.raises(Denied):
        setup.admit(TaskSpec('x', capability='exec.shell'))


def test_action_kind_not_bypassable(setup):
    t = setup.admit(TaskSpec('safe'))
    a = Action(t['id'], 'exec.shell', 'local', {'command':'rm -rf /'}, 'model.text', Risk.LOW, 'malicious')
    with pytest.raises(Denied):
        setup.gate.authorize(a, OP)


def test_idempotency_checks_dependencies(setup):
    parent = setup.admit(TaskSpec('parent'))
    setup.admit(TaskSpec('task', idempotency_key='dependency-key'))
    with pytest.raises(Conflict):
        setup.admit(TaskSpec('task', idempotency_key='dependency-key', dependencies=(parent['id'],)))
