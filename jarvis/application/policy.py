"""Authorization rules with persistence accessed exclusively via a typed repository port.

LLM output never authorizes an action. Only the built-in side-effect-free echo is
registered in this milestone. OS sandboxing remains an independent requirement.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from ..domain.contracts import Action, Denied, Risk
from .ports import TaskRepository


@dataclass(frozen=True)
class Principal:
    identity: str
    capabilities: frozenset[str]


class ActionGate:
    """Application authority; persistence owns atomic approval and action records."""

    def __init__(self, store: TaskRepository) -> None:
        self.store = store

    def request_approval(self, action: Action, principal: Principal, ttl: int = 300) -> str:
        self._precheck(action, principal)
        if action.risk not in (Risk.HIGH, Risk.CRITICAL):
            raise Denied('Approval not applicable to low/medium risk')
        if not 1 <= ttl <= 3600:
            raise Denied('Invalid expiry')
        approval_id = str(uuid4())
        self.store.record_approval(approval_id, action.task_id, action.digest(), ttl)
        return approval_id

    def grant_approval(self, approval_id: str, *, human_confirmation: str) -> str:
        """Out-of-band local operator approval; never through the task HTTP API."""
        if human_confirmation != approval_id:
            raise Denied('Operator must explicitly type the matching approval identifier')
        self.store.grant_approval_record(approval_id)
        return approval_id

    def _precheck(self, action: Action, principal: Principal) -> None:
        # New external executors cannot be enabled simply by adding an adapter.
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
        self.store.authorize_action_record(
            digest, action.task_id, action.kind,
            requires_approval=action.risk in (Risk.HIGH, Risk.CRITICAL),
            approval_id=approval_id,
        )
        return digest

    def finalize(self, digest: str, outcome: dict, *, verified: bool) -> None:
        self.store.finalize_action_record(digest, outcome, verified=verified)
