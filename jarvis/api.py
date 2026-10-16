"""Loopback-only, token-authenticated developer HTTP control surface. No frontend."""
import hmac
import os

from .contracts import Conflict, Denied, Risk, TaskSpec
from .engine import Engine
from .policy import Principal
from .storage import Store


def create_app(store: Store | None = None, secret: str | None = None):
    try:
        from fastapi import FastAPI, Header, HTTPException
        from pydantic import BaseModel, Field
    except ImportError as exc:
        raise RuntimeError('Install: pip install -e .[api]') from exc
    token = secret if secret is not None else os.getenv('JARVIS_OPERATOR_TOKEN', '')
    if len(token) < 24:
        raise RuntimeError('JARVIS_OPERATOR_TOKEN must contain at least 24 characters')
    db = store or Store(os.getenv('JARVIS_DB', 'jarvis.sqlite3'))
    db.reconcile_interrupted()
    engine = Engine(db)
    app = FastAPI(title='JARVIS Core developer API', version='0.1.0', docs_url=None, redoc_url=None)

    class CreateTask(BaseModel):
        objective: str = Field(min_length=1, max_length=16000)
        category: str = 'analysis'
        capability: str = 'model.text'
        risk: Risk = Risk.LOW
        idempotency_key: str | None = None
        parent_id: str | None = None
        dependencies: list[str] = Field(default_factory=list, max_length=32)

    def authenticate(value: str | None) -> Principal:
        if not value or not hmac.compare_digest(value, f'Bearer {token}'):
            raise HTTPException(status_code=401, detail='Unauthorized')
        return Principal('local-operator', frozenset({'model.text'}))

    def fail(exc: Exception):
        if isinstance(exc, KeyError):
            raise HTTPException(status_code=404, detail='Task not found') from exc
        if isinstance(exc, Conflict):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if isinstance(exc, Denied):
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        raise exc

    @app.get('/health')
    def health() -> dict:
        return {'status': 'ok', 'component': 'jarvis-core', 'api_version': 1}

    @app.post('/v1/tasks')
    def create_task(body: CreateTask, authorization: str | None = Header(default=None)):
        authenticate(authorization)
        try:
            return engine.admit(TaskSpec(**body.model_dump(exclude={'dependencies'}), dependencies=tuple(body.dependencies)))
        except (Denied, Conflict, KeyError) as exc:
            fail(exc)

    @app.get('/v1/tasks/{task_id}')
    def get_task(task_id: str, authorization: str | None = Header(default=None)):
        authenticate(authorization)
        try:
            return db.get(task_id)
        except KeyError as exc:
            fail(exc)

    @app.get('/v1/tasks/{task_id}/events')
    def history(task_id: str, authorization: str | None = Header(default=None)):
        authenticate(authorization)
        try:
            db.get(task_id)
            return db.history(task_id)
        except KeyError as exc:
            fail(exc)

    @app.post('/v1/tasks/{task_id}/approval-request')
    def approval_request(task_id: str, authorization: str | None = Header(default=None)):
        principal = authenticate(authorization)
        try:
            return {'approval_id': engine.request_approval(task_id, principal), 'warning': 'This is a proposal, not a grant.'}
        except (Denied, Conflict, KeyError) as exc:
            fail(exc)

    class RunOptions(BaseModel):
        approval_id: str | None = None

    @app.post('/v1/tasks/{task_id}/run-echo')
    def run_echo(task_id: str, options: RunOptions, authorization: str | None = Header(default=None)):
        principal = authenticate(authorization)
        try:
            result = engine.run_echo(task_id, principal, approval_id=options.approval_id)
            return {'output': result.output, 'provider': result.provider, 'evidence': result.evidence}
        except (Denied, Conflict, KeyError) as exc:
            fail(exc)

    @app.post('/v1/tasks/{task_id}/cancel')
    def cancel(task_id: str, authorization: str | None = Header(default=None)):
        authenticate(authorization)
        try:
            return engine.cancel(task_id)
        except (Denied, Conflict, KeyError) as exc:
            fail(exc)

    @app.post('/v1/tasks/{task_id}/resume-dependencies')
    def resume(task_id: str, authorization: str | None = Header(default=None)):
        authenticate(authorization)
        try:
            return engine.resume_dependencies(task_id)
        except (Denied, Conflict, KeyError) as exc:
            fail(exc)
    return app

app = None  # Uvicorn uses jarvis.api:serve for fail-closed startup.
def serve():
    import uvicorn
    host = os.getenv('JARVIS_BIND', '127.0.0.1')
    if host not in ('127.0.0.1', '::1'):
        raise RuntimeError('Only loopback binding is supported in v0.1')
    uvicorn.run(create_app(), host=host, port=int(os.getenv('JARVIS_PORT', '8765')))
