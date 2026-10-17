"""Policy/repository isolation and atomic high-risk approval invariants."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from jarvis.application.policy import ActionGate, Principal
from jarvis.domain.contracts import Action, Conflict, Denied, Risk, TaskSpec
from jarvis.application.engine import Engine
from jarvis.persistence.sqlite import Store


OP = Principal('local-operator', frozenset({'model.text'}))


def test_policy_authorization_does_not_require_database_specific_attributes():
    called = []
    action = Action('task-1', 'builtin.echo', 'local', {'text': 'hello'},
                    'model.text', Risk.LOW, 'echo:task-1')
    fake = SimpleNamespace(
        get=lambda _id: {'capability': 'model.text', 'status': 'READY', 'risk': 'LOW'},
        authorize_action_record=lambda *args, **kwargs: called.append((args, kwargs)),
    )
    assert ActionGate(fake).authorize(action, OP) == action.digest()
    assert len(called) == 1
    assert called[0][0] == (action.digest(), 'task-1', 'builtin.echo')
    assert called[0][1]['requires_approval'] is False


def test_high_risk_approval_is_consumed_once_under_parallel_requests(tmp_path):
    store = Store(str(tmp_path / 'concurrent-approval.db'))
    try:
        engine = Engine(store)
        task = engine.admit(TaskSpec('authorized local echo', risk=Risk.HIGH))
        action = engine.propose_echo(task['id'])
        approval = engine.request_approval(task['id'], OP)
        engine.gate.grant_approval(approval, human_confirmation=approval)

        def authorize(_):
            try:
                return engine.gate.authorize(action, OP, approval)
            except Conflict:
                return None

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(authorize, range(24)))
        assert results.count(action.digest()) == 1
        assert results.count(None) == 23
        assert store.db.execute(
            'SELECT COUNT(*) FROM actions WHERE task_id=?', (task['id'],)
        ).fetchone()[0] == 1
        row = store.db.execute('SELECT consumed_at FROM approvals WHERE id=?', (approval,)).fetchone()
        assert row['consumed_at'] is not None
    finally:
        store.close()


def test_failed_approval_does_not_consume_a_valid_approval(tmp_path):
    store = Store(str(tmp_path / 'rollback.db'))
    try:
        engine = Engine(store)
        task = engine.admit(TaskSpec('echo', risk=Risk.HIGH))
        approved = engine.propose_echo(task['id'])
        bad = Action(approved.task_id, approved.kind, approved.target,
                     {'text': 'modified'}, approved.capability, approved.risk, approved.key)
        approval = engine.request_approval(task['id'], OP)
        engine.gate.grant_approval(approval, human_confirmation=approval)
        with pytest.raises(Denied):
            engine.gate.authorize(bad, OP, approval)
        row = store.db.execute('SELECT consumed_at FROM approvals WHERE id=?', (approval,)).fetchone()
        assert row['consumed_at'] is None
        assert engine.gate.authorize(approved, OP, approval) == approved.digest()
    finally:
        store.close()
