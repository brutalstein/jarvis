"""Compatibility facade; integration implementations are provider-specific modules."""
from .integrations.errors import NotConfigured
from .integrations.process import checked_process
from .integrations.gemini import gemini_text
from .integrations.n8n import N8N
from .integrations.openclaw import OpenClaw

__all__ = ["NotConfigured", "checked_process", "gemini_text", "N8N", "OpenClaw"]
