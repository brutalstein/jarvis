"""Offline contract tests; do not confuse mock transports with live service verification."""
import asyncio
import json
import sys

import httpx
import pytest

from jarvis.adapters import N8N, OpenClaw, checked_process
from jarvis.contracts import Denied


def test_n8n_readonly_contract_with_mock_transport(monkeypatch):
    seen = []

    def respond(request):
        seen.append((request.method, request.url.path, request.headers.get('X-N8N-API-KEY')))
        return httpx.Response(200, json={'data': [{'id': 'workflow-1'}]})

    transport = httpx.MockTransport(respond)
    actual_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: actual_client(transport=transport, **kwargs))
    result = asyncio.run(N8N('https://example.net', 'test-secret').workflows())
    assert result == {'data': [{'id': 'workflow-1'}]}
    assert seen == [('GET', '/api/v1/workflows', 'test-secret')]


def test_openclaw_readonly_gateway_contract():
    import websockets

    async def handle(ws):
        await ws.send(json.dumps({'type': 'event', 'event': 'connect.challenge',
                                  'payload': {'nonce': 'nonce', 'ts': 1000}}))
        connect = json.loads(await ws.recv())
        assert connect['method'] == 'connect'
        assert connect['params']['scopes'] == ['operator.read']
        await ws.send(json.dumps({'type': 'res', 'id': connect['id'], 'ok': True,
                                  'payload': {'type': 'hello-ok', 'protocol': 4,
                                              'auth': {'scopes': ['operator.read']}}}))
        request = json.loads(await ws.recv())
        assert request['method'] == 'health'
        await ws.send(json.dumps({'type': 'res', 'id': request['id'], 'ok': True,
                                  'payload': {'ok': True}}))

    async def scenario():
        async with websockets.serve(handle, '127.0.0.1', 0) as server:
            port = server.sockets[0].getsockname()[1]
            gateway = OpenClaw(f'ws://127.0.0.1:{port}', 'test-token')
            assert await gateway.rpc('health') == {'ok': True}
            with pytest.raises(Denied):
                await gateway.rpc('agent', {'message': 'unapproved'})

    asyncio.run(scenario())


def test_openclaw_refuses_negotiated_scope_downgrade():
    import websockets

    async def handle(ws):
        await ws.send(json.dumps({'type': 'event', 'event': 'connect.challenge'}))
        connect = json.loads(await ws.recv())
        await ws.send(json.dumps({'type': 'res', 'id': connect['id'], 'ok': True,
                                  'payload': {'type': 'hello-ok', 'protocol': 4,
                                              'auth': {'scopes': []}}}))

    async def scenario():
        async with websockets.serve(handle, '127.0.0.1', 0) as server:
            port = server.sockets[0].getsockname()[1]
            with pytest.raises(Denied, match='scope'):
                await OpenClaw(f'ws://127.0.0.1:{port}', 'test-token').rpc('health')

    asyncio.run(scenario())


def test_process_wrapper_rejects_oversize_output(tmp_path):
    # Local subprocess only; no network, no shell, no provider.
    with pytest.raises(Denied, match='output exceeds'):
        asyncio.run(checked_process(sys.executable,
                    ['-c', "print('x'*2000)"], cwd=tmp_path,
                    timeout=8, output_limit=1024))
