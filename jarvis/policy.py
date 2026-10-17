"""Compatibility facade; use jarvis.application.policy in new code."""
from .application.policy import ActionGate, Principal

__all__ = ["ActionGate", "Principal"]
