"""Explicit action policy: execution is denied unless capability and exact scope are authorized."""
from __future__ import annotations
from dataclasses import dataclass
import hmac
import json
import time
from uuid import uuid4

from ..domain.contracts import Action, Conflict, Denied, Risk
from ..persistence.sqlite import Store, utc

@dataclass(frozen=True)
class Principal:
    identity: str
    capabilities: frozenset[str]

class ActionGate:
    """Only cooperative adapters can be mediated; OS sandboxing is a separate boundary."""
    def __init__(self, store: Store) -> None:
        self.store = store

    def request_approval(self, action: Action, principal: Principal, ttl: int = 300) -> str:
        self._precheck(action, principal)
        if action.risk not in (Risk.HIGH, Risk.CRITICAL):
            raise Denied('Approval not applicable to low/medium risk')
        if not 1 <= ttl <= 3600:
            raise Denied('Invalid expiry')
        approval_id = str(uuid4())
        with self.store.tx():
            self.store.db.execute('INSERT INTO approvals(id,task_id,action_digest,expires_at,created_at) VALUES(?,?,?,?,?)',
                                  (approval_id, action.task_id, action.digest(), time.time() + ttl, utc()))
            self.store.event(action.task_id, 'approval.requested', {'approval_id': approval_id, 'digest': action.digest()})
        return approval_id

    def grant_approval(self, approval_id: str, *, human_confirmation: str) -> str:
        """Out-of-band local operator approval; never expose via the task HTTP API."""
        if human_confirmation != approval_id:
            raise Denied('Operator must explicitly type the matching approval identifier')
        with self.store.tx():
            row = self.store.db.execute('SELECT * FROM approvals WHERE id=?', (approval_id,)).fetchone()
            if not row or row['expires_at'] <= time.time() or row['granted_at'] is not None:
                raise Denied('Unknown, expired or already granted approval')
            self.store.db.execute('UPDATE approvals SET granted_at=? WHERE id=?', (time.time(), approval_id))
            self.store.event(row['task_id'], 'approval.granted', {'id': approval_id, 'digest': row['action_digest']})
        return approval_id

    def _precheck(self, action: Action, principal: Principal) -> None:
        # In v0.1 the only executable kind is built-in, local and side-effect-free.
        # Additional executors require a reviewed policy registry, not generic passthrough.
        if (action.kind, action.target, action.capability) != ('builtin.echo', 'local', 'model.text'):
            raise Denied('Action kind/target not registered for execution')
        if not principal.identity or action.capability not in principal.capabilities:
            raise Denied('Missing delegated capability')
        task = self.store.get(action.task_id)
        if task['capability'] != action.capability:
            raise Denied('Action exceeds admitted task capability')
        if task['status'] not in ('READY', 'RUNNING', 'WAITING_FOR_APPROVAL'):
            raise Denied('Task not in executable state')
        if Risk(task['risk']) != action.risk:
            raise Denied('Risk mismatch: action requires fresh admission')
        if not action.target or not action.kind or not action.key:
            raise Denied('Incomplete action identity')

    def authorize(self, action: Action, principal: Principal, approval_id: str | None = None) -> str:
        self._precheck(action, principal)
        digest = action.digest()
        with self.store.tx():
            prior = self.store.db.execute('SELECT status FROM actions WHERE action_digest=?', (digest,)).fetchone()
            if prior:
                raise Conflict(f'Action already admitted with state {prior["status"]}')
            if action.risk in (Risk.HIGH, Risk.CRITICAL):
                row = self.store.db.execute('SELECT * FROM approvals WHERE id=? AND task_id=?',
                                            (approval_id, action.task_id)).fetchone()
                if not row or not hmac.compare_digest(row['action_digest'], digest) or row['granted_at'] is None or row['consumed_at'] is not None or row['expires_at'] <= time.time():
                    raise Denied('Valid single-use, exact-action approval required')
                self.store.db.execute('UPDATE approvals SET consumed_at=? WHERE id=? AND consumed_at IS NULL',
                                      (time.time(), approval_id))
            self.store.db.execute('INSERT INTO actions(action_digest,task_id,status,at) VALUES(?,?,?,?)',
                                  (digest, action.task_id, 'INTENT_RECORDED', utc()))
            self.store.event(action.task_id, 'action.authorized', {'digest': digest, 'kind': action.kind})
        return digest

    def finalize(self, digest: str, outcome: dict, *, verified: bool) -> None:
        with self.store.tx():
            row = self.store.db.execute('SELECT task_id,status FROM actions WHERE action_digest=?', (digest,)).fetchone()
            if not row or row['status'] != 'INTENT_RECORDED':
                raise Conflict('No unfinished action intention')
            status = 'VERIFIED' if verified else 'RECOVERY_REQUIRED'
            self.store.db.execute('UPDATE actions SET status=?,outcome=? WHERE action_digest=?',
                                  (status, json.dumps(outcome, sort_keys=True), digest))
            self.store.event(row['task_id'], 'action.finalized', {'digest': digest, 'status': status})
