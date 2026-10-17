"""Domain contracts and deterministic admission validation."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any

class State(StrEnum):
    CREATED = 'CREATED'
    VALIDATING = 'VALIDATING'
    PLANNING = 'PLANNING'
    READY = 'READY'
    RUNNING = 'RUNNING'
    WAITING_FOR_APPROVAL = 'WAITING_FOR_APPROVAL'
    WAITING_FOR_DEPENDENCY = 'WAITING_FOR_DEPENDENCY'
    VERIFYING = 'VERIFYING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'
    BLOCKED = 'BLOCKED'
    RECOVERY_REQUIRED = 'RECOVERY_REQUIRED'

TERMINAL = frozenset({State.COMPLETED, State.FAILED, State.CANCELLED, State.BLOCKED})
TRANSITIONS: dict[State, frozenset[State]] = {
    State.CREATED: frozenset({State.VALIDATING, State.CANCELLED}),
    State.VALIDATING: frozenset({State.PLANNING, State.BLOCKED, State.FAILED, State.CANCELLED}),
    State.PLANNING: frozenset({State.READY, State.WAITING_FOR_APPROVAL, State.WAITING_FOR_DEPENDENCY, State.BLOCKED, State.FAILED, State.CANCELLED}),
    State.READY: frozenset({State.RUNNING, State.CANCELLED, State.BLOCKED}),
    State.RUNNING: frozenset({State.VERIFYING, State.FAILED, State.CANCELLED, State.RECOVERY_REQUIRED}),
    State.WAITING_FOR_APPROVAL: frozenset({State.READY, State.BLOCKED, State.CANCELLED}),
    State.WAITING_FOR_DEPENDENCY: frozenset({State.READY, State.BLOCKED, State.CANCELLED}),
    State.VERIFYING: frozenset({State.COMPLETED, State.FAILED, State.RECOVERY_REQUIRED}),
    State.COMPLETED: frozenset(),
    State.FAILED: frozenset(),
    State.CANCELLED: frozenset(),
    State.BLOCKED: frozenset(),
    State.RECOVERY_REQUIRED: frozenset({State.READY, State.BLOCKED, State.CANCELLED}),
}

class Risk(StrEnum):
    LOW = 'LOW'
    MEDIUM = 'MEDIUM'
    HIGH = 'HIGH'
    CRITICAL = 'CRITICAL'

class CoreError(Exception):
    pass

class Conflict(CoreError):
    pass

class Denied(CoreError):
    pass

class UncertainOutcome(CoreError):
    """External action may have committed; do not retry automatically."""

@dataclass(frozen=True)
class Action:
    task_id: str
    kind: str
    target: str
    parameters: dict[str, Any]
    capability: str
    risk: Risk
    key: str

    def digest(self) -> str:
        canonical = json.dumps({"task": self.task_id, "kind": self.kind, "target": self.target,
            "parameters": self.parameters, "capability": self.capability, "risk": self.risk.value,
            "key": self.key}, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        return sha256(canonical.encode()).hexdigest()

@dataclass(frozen=True)
class Capability:
    name: str
    categories: frozenset[str]
    enabled: bool = False
    max_cost: float = 0
    priority: int = 100
    supports_tools: bool = False
    operations: frozenset[str] = field(default_factory=lambda: frozenset({'model.text'}))
    authenticated: bool = True
    healthy: bool = True

@dataclass(frozen=True)
class TaskSpec:
    objective: str
    category: str = 'analysis'
    capability: str = 'model.text'
    risk: Risk = Risk.LOW
    idempotency_key: str | None = None
    parent_id: str | None = None
    dependencies: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        if not (1 <= len(self.objective.strip()) <= 16000):
            raise Denied('Objective must contain 1..16000 characters')
        if self.category not in {'analysis', 'planning', 'coding', 'browser', 'automation'}:
            raise Denied('Unsupported task category')
        if self.capability not in {'model.text', 'browser.navigate', 'workflow.trigger', 'coding.review'}:
            raise Denied('Unknown capability')
        if self.idempotency_key is not None and not (1 <= len(self.idempotency_key) <= 128):
            raise Denied('Invalid idempotency key')
        if len(set(self.dependencies)) != len(self.dependencies):
            raise Denied('Duplicate dependency')
