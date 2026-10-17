"""Restricted OpenClaw Gateway read-only client."""
from __future__ import annotations
import asyncio
import json
from typing import Any
from urllib.parse import urlparse
from ..domain.contracts import Denied
from .errors import NotConfigured

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
                        hello = frame.get('payload')
                        if not isinstance(hello, dict) or hello.get('type') != 'hello-ok' or hello.get('protocol') != 4:
                            raise Denied('Incompatible OpenClaw handshake')
                        auth = hello.get('auth')
                        if not isinstance(auth, dict) or 'operator.read' not in auth.get('scopes', []):
                            raise Denied('OpenClaw did not grant read scope')
                        break
                reqid = str(uuid4())
                await ws.send(json.dumps({'type':'req','id':reqid,'method':method,'params':params or {}}))
                while True:
                    frame = json.loads(await ws.recv())
                    if frame.get('type') == 'res' and frame.get('id') == reqid:
                        if not frame.get('ok'):
                            raise Denied('OpenClaw RPC failed')
                        return frame.get('payload')
