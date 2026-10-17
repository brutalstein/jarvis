"""Compatibility facade; use jarvis.application.engine in new code."""
from .application.engine import Engine, ExecutionResult

__all__ = ["Engine", "ExecutionResult"]
