"""Read-only n8n API adapter, separate from n8n task ingress."""
from __future__ import annotations
from typing import Any
from urllib.parse import urlparse
from ..domain.contracts import Denied
from .errors import NotConfigured

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
