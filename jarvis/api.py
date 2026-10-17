"""Compatibility facade for existing imports and uvicorn CLI entry."""
from .entrypoints.http import app, create_app, serve

__all__ = ["app", "create_app", "serve"]
