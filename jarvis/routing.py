"""Deterministic capability router: no model self-reported confidence is used."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import Capability, Denied

@dataclass(frozen=True)
class RouteRequest:
    category: str
    capability: str
    allowed_providers: frozenset[str]
    max_cost: float = 0.0
    needs_tools: bool = False

@dataclass(frozen=True)
class RouteDecision:
    provider: str
    explanation: str

class Router:
    def __init__(self, registry: list[Capability]) -> None:
        if len({c.name for c in registry}) != len(registry):
            raise ValueError('Duplicate provider')
        self.registry = registry

    def choose(self, request: RouteRequest) -> RouteDecision:
        candidates = [p for p in self.registry if p.enabled
                      and p.name in request.allowed_providers
                      and request.category in p.categories
                      and request.capability in p.operations
                      and p.authenticated and p.healthy
                      and (not request.needs_tools or p.supports_tools)
                      and p.max_cost <= request.max_cost]
        if not candidates:
            raise Denied('No compatible provider within access/budget constraints')
        chosen = min(candidates, key=lambda p: (p.priority, p.max_cost, p.name))
        return RouteDecision(chosen.name, f'authorized={chosen.name}; priority={chosen.priority}; deterministic tie-break')
