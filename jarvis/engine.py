"""Admission, state transitions, guarded execution, and verification.

v0.1 executor is deliberately constrained to deterministic echo: live agents are opt-in,
not delegated unrestricted privileges. Registered integrations are in adapters.py.
"""
from __future__ import annotations
from dataclasses import dataclass
import time
from uuid import uuid4

from .contracts import Action, Conflict, Denied, Risk, State, TaskSpec
from .policy import ActionGate, Principal
from .storage import Store

@dataclass(frozen=True)
class ExecutionResult:
    output: str
    provider: str
    evidence: dict

class Engine:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.gate = ActionGate(store)

    def admit(self, spec: TaskSpec) -> dict:
        task = self.store.create(spec)
        tid = task['id']
        # Only one concurrent admission may advance a newly created task.
        if not self.store.claim_admission(tid):
            return self.store.get(tid)
        self.store.transition(tid, State.PLANNING)
        if spec.dependencies and any(self.store.get(d)['status'] != State.COMPLETED for d in spec.dependencies):
            return self.store.transition(tid, State.WAITING_FOR_DEPENDENCY)
        if spec.risk in (Risk.HIGH, Risk.CRITICAL):
            return self.store.transition(tid, State.WAITING_FOR_APPROVAL)
        return self.store.transition(tid, State.READY)

    def resume_dependencies(self, task_id: str) -> dict:
        if self.store.get(task_id)['status'] != State.WAITING_FOR_DEPENDENCY:
            raise Conflict('Not waiting for dependencies')
        return self.store.transition(task_id, State.READY)

    def propose_echo(self, task_id: str) -> Action:
        task = self.store.get(task_id)
        if task['capability'] != 'model.text' or task['category'] not in ('analysis','planning'):
            raise Denied('Built-in echo supports analysis/planning only')
        return Action(task_id, 'builtin.echo', 'local', {'text': task['objective']},
                      'model.text', Risk(task['risk']), key=f'echo:{task_id}')

    def request_approval(self, task_id: str, principal: Principal, ttl: int = 300) -> str:
        action = self.propose_echo(task_id)
        return self.gate.request_approval(action, principal, ttl)

    def run_echo(self, task_id: str, principal: Principal, *, approval_id: str | None = None,
                 worker_id: str | None = None, lease_seconds: float = 60) -> ExecutionResult:
        """A real local deterministic execution path; not a simulated model integration."""
        task = self.store.get(task_id)
        action = self.propose_echo(task_id)
        worker = worker_id or str(uuid4())
        if task['status'] == State.WAITING_FOR_APPROVAL:
            # Exact approval must be consumed while the task is still waiting.
            digest = self.gate.authorize(action, principal, approval_id)
            self.store.transition(task_id, State.READY)
            if not self.store.lease(task_id, worker, time.time(), lease_seconds):
                self.gate.finalize(digest, {'reason': 'lease unavailable'}, verified=False)
                raise Conflict('Action admitted but lease unavailable; reconciliation required')
        elif task['status'] == State.READY:
            # Acquire ownership *before* recording the low-risk action intention.
            if not self.store.lease(task_id, worker, time.time(), lease_seconds):
                raise Conflict('Task already leased; no action admitted')
            try:
                digest = self.gate.authorize(action, principal, approval_id)
            except BaseException:
                self.store.release(task_id, worker)
                raise
        else:
            raise Conflict('Task not ready')
        try:
            self.store.transition(task_id, State.RUNNING, owner=worker)
            output = action.parameters['text']
            # Contract verification: exact equality and no external effects. NOT semantic truth verification.
            verified = isinstance(output, str) and output == task['objective']
            self.store.transition(task_id, State.VERIFYING, owner=worker)
            evidence = {'checker': 'builtin.echo.equal', 'passed': verified,
                        'external_side_effects': False, 'action_digest': digest}
            self.gate.finalize(digest, evidence, verified=verified)
            if verified:
                self.store.transition(task_id, State.COMPLETED,
                    {'verified': True, 'evidence': evidence, 'result': output}, owner=worker)
            else:
                self.store.transition(task_id, State.FAILED, {'evidence': evidence}, owner=worker)
            return ExecutionResult(output, 'builtin.echo', evidence)
        except Exception as exc:
            current = State(self.store.get(task_id)['status'])
            if current in (State.READY, State.RUNNING, State.VERIFYING):
                self.store.quarantine(task_id, f'execution error: {type(exc).__name__}', owner=worker)
            raise
        finally:
            self.store.release(task_id, worker)

    def cancel(self, task_id: str) -> dict:
        task = self.store.get(task_id)
        current = State(task['status'])
        if current in (State.RUNNING, State.VERIFYING):
            raise Denied('Cannot claim cancelled while active; signal worker and reconcile first')
        return self.store.transition(task_id, State.CANCELLED)
