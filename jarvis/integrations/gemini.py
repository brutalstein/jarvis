"""Optional Gemini CLI adapter: execution must be separately authorized."""
from __future__ import annotations
import json
from pathlib import Path
from ..domain.contracts import Denied
from .process import checked_process

async def gemini_text(prompt: str, workspace: Path, *, program: str = 'gemini') -> str:
    # Official Gemini CLI headless JSON mode; allowlisted read-only prompts by policy.
    raw = await checked_process(program, ['--prompt', prompt, '--output-format', 'json'], cwd=workspace)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Denied('Gemini returned invalid JSON') from exc
    if not isinstance(obj, dict) or not isinstance(obj.get('response'), str):
        raise Denied('Gemini missing documented response field')
    return obj['response']
