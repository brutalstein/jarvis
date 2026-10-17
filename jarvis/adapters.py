"""External boundaries. No adapter is allowed to make an independent approval decision."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from .contracts import Denied, UncertainOutcome

class NotConfigured(Denied):
    pass

async def checked_process(program: str, args: list[str], *, cwd: Path, timeout: float = 90, output_limit: int = 2_000_000) -> str:
    """Trusted executable only. No shell; bounded pipe reads; scrub unrelated env secrets.

    This is NOT OS isolation. A malicious executable can still access the caller's files.
    Do not route arbitrary LLM-generated commands here.
    """
    if not cwd.is_dir() or timeout <= 0 or not 1024 <= output_limit <= 2_000_000:
        raise Denied('Invalid process boundary')
    if not Path(program).name or any('\x00' in a for a in args):
        raise Denied('Invalid subprocess parameters')
    safe_env = {k: v for k, v in os.environ.items() if k.upper() in {
        'PATH', 'HOME', 'USERPROFILE', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG',
        'GOOGLE_API_KEY', 'GEMINI_API_KEY', 'APPDATA', 'LOCALAPPDATA'}}
    proc = await asyncio.create_subprocess_exec(program, *args, cwd=cwd, env=safe_env,
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    async def bounded(stream: asyncio.StreamReader) -> bytes:
        result = bytearray()
        while chunk := await stream.read(65536):
            result.extend(chunk)
            if len(result) > output_limit:
                raise Denied('Provider output exceeds configured size limit')
        return bytes(result)

    stdout_task = asyncio.create_task(bounded(proc.stdout))
    stderr_task = asyncio.create_task(bounded(proc.stderr))
    try:
        _code, stdout, _stderr = await asyncio.wait_for(asyncio.gather(
            proc.wait(), stdout_task, stderr_task), timeout)
    except (TimeoutError, Denied, asyncio.CancelledError) as exc:
        if proc.returncode is None:
            proc.kill()
        stdout_task.cancel()
        stderr_task.cancel()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        await proc.wait()
        if isinstance(exc, TimeoutError):
            raise UncertainOutcome('Provider exceeded time budget; side effects unverified') from None
        raise
    if proc.returncode != 0:
        raise Denied(f'Provider failed with exit code {proc.returncode}; sensitive diagnostics suppressed')
    return stdout.decode('utf-8', errors='replace')

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

class N8N:
    def __init__(self, base_url: str, api_key: str) -> None:
        p = urlparse(base_url)
        if p.scheme != 'https' and not (p.scheme == 'http' and p.hostname in ('127.0.0.1','localhost')):
            raise Denied('n8n must use HTTPS or local-only HTTP')
        if p.username or p.password or not api_key:
            raise NotConfigured('n8n URL/key invalid')
        self.base = base_url.rstrip('/')
        self.key = api_key

    async def workflows(self) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:
            raise NotConfigured('Install integrations extra for n8n') from exc
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.get(f'{self.base}/api/v1/workflows', headers={'X-N8N-API-KEY': self.key})
            response.raise_for_status()
            obj = response.json()
            if not isinstance(obj, dict):
                raise Denied('Invalid n8n response')
            return obj

class OpenClaw:
    """Direct trusted local backend Gateway handshake for protocol v4.

    Pins a specific wire protocol; does not claim universal OpenClaw compatibility.
    """
    def __init__(self, url: str, token: str) -> None:
        p = urlparse(url)
        if p.scheme != 'ws' or p.hostname not in ('localhost','127.0.0.1') or not token:
            raise Denied('Only authenticated loopback ws Gateway supported in v0.1')
        self.url, self.token = url, token

    async def rpc(self, method: str, params: dict | None = None, *, timeout: int = 20) -> Any:
        if method not in {'health', 'status', 'sessions.list'}:
            raise Denied('RPC outside pinned read-only allowlist')
        try:
            import websockets
        except ImportError as exc:
            raise NotConfigured('Install integrations extra for OpenClaw') from exc
        import sys
        from uuid import uuid4
        async with asyncio.timeout(timeout):
            async with websockets.connect(self.url, max_size=1_000_000) as ws:
                # Challenge may arrive before handshake. No device registration is required for backend on loopback.
                first = json.loads(await ws.recv())
                if first.get('type') != 'event' or first.get('event') != 'connect.challenge':
                    raise Denied('Unexpected OpenClaw handshake')
                ident = str(uuid4())
                await ws.send(json.dumps({'type':'req','id':ident,'method':'connect','params':{
                    'minProtocol':4,'maxProtocol':4,
                    'client':{'id':'gateway-client','version':'0.1.0','platform':sys.platform,'mode':'backend'},
                    'role':'operator','scopes':['operator.read'],'caps':[], 'commands':[], 'permissions':{},
                    'auth':{'token':self.token},'locale':'en-US','userAgent':'jarvis-core/0.1.0'}}))
                while True:
                    frame = json.loads(await ws.recv())
                    if frame.get('type') == 'res' and frame.get('id') == ident:
                        if not frame.get('ok'):
                            raise Denied('OpenClaw connect failed')
                        break
                reqid = str(uuid4())
                await ws.send(json.dumps({'type':'req','id':reqid,'method':method,'params':params or {}}))
                while True:
                    frame = json.loads(await ws.recv())
                    if frame.get('type') == 'res' and frame.get('id') == reqid:
                        if not frame.get('ok'):
                            raise Denied('OpenClaw RPC failed')
                        return frame.get('payload')
