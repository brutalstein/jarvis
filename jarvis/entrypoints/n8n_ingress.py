"""Opt-in, least-privilege n8n HTTP intake, isolated from general operator routes.

n8n has no right to select a model, tool, task risk level, or external side effect.
This route remains a bounded local echo demonstration until sandboxed agent execution exists.
"""

import hmac
import os
from typing import Callable, NoReturn

from ..application.engine import Engine
from ..application.policy import Principal
from ..application.ports import TaskRepository
from ..domain.contracts import Conflict, Denied, Risk, State, TaskSpec


def install_n8n_ingress(
    app: object, engine: Engine, db: TaskRepository,
    token: str, fail: Callable[[Exception], NoReturn],
) -> None:
    from fastapi import Header, HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, ConfigDict, Field

    # Intentionally narrow n8n ingress. The workflow token can ONLY request a
    # deterministic, local, side-effect-free echo task; it is not an operator token.
    # No arbitrary category, risk, provider or tool fields are accepted.
    class N8nEchoRequest(BaseModel):
        model_config = ConfigDict(extra='forbid')
        workflow_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,48}$')
        execution_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,48}$')
        objective: str = Field(min_length=1, max_length=2000)

    @app.post('/v1/integrations/n8n/echo')
    def n8n_echo(body: N8nEchoRequest, x_jarvis_n8n_token: str | None = Header(default=None)):
        n8n_token = os.getenv('JARVIS_N8N_INGEST_TOKEN', '')
        allowed = {
            value.strip() for value in os.getenv('JARVIS_N8N_WORKFLOW_IDS', '').split(',')
            if value.strip()
        }
        # Fail-closed without a separately provisioned, suitably long secret and
        # explicit workflow allowlist. Nothing shares the operator bearer token.
        if (len(n8n_token) < 32 or hmac.compare_digest(n8n_token, token)
                or not x_jarvis_n8n_token or not hmac.compare_digest(
                    n8n_token, x_jarvis_n8n_token)):
            raise HTTPException(status_code=401, detail='Invalid n8n integration credential')
        if body.workflow_id not in allowed:
            raise HTTPException(status_code=403, detail='Workflow is not authorized')
        principal = Principal(f'n8n:{body.workflow_id}', frozenset({'model.text'}))
        try:
            task = engine.admit(TaskSpec(
                objective=body.objective, category='analysis', capability='model.text',
                risk=Risk.LOW,
                idempotency_key=f'n8n:{body.workflow_id}:{body.execution_id}',
            ))
            if task['status'] == State.READY:
                try:
                    engine.run_echo(task['id'], principal)
                except Conflict:
                    # Another concurrent delivery may own this exact task.
                    # A repeat must NEVER create a second execution.
                    pass
            current = db.get(task['id'])
            if current['status'] == State.COMPLETED:
                return {'task_id': task['id'], 'status': 'COMPLETED',
                        'result': body.objective, 'verified': True}
            if current['status'] in (State.RECOVERY_REQUIRED, State.FAILED, State.BLOCKED):
                raise HTTPException(status_code=409, detail='Task requires operator reconciliation')
            return JSONResponse(status_code=202,
                                content={'task_id': task['id'], 'status': current['status'],
                                         'verified': False})
        except (Denied, Conflict, KeyError) as exc:
            fail(exc)
