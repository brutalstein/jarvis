"""Compatibility facade; use jarvis.domain.routing in new code."""
from .domain.routing import RouteDecision, RouteRequest, Router

__all__ = ["RouteDecision", "RouteRequest", "Router"]
