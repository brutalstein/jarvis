# JARVIS Core

**A local-first, fail-closed task authority for AI-agent workflows.** Status: **v0.1 foundation; not production-ready; not a fully connected autonomous assistant**.

The first commit intentionally favors executable policy/state-machine guarantees over misleading dummy integrations. JARVIS Core owns task admission, durable transitions, action-intent journaling, scoped human approval and verification. OpenClaw owns agent sessions; Browser Use owns browser sessions; n8n owns workflow triggers; LLMs are untrusted execution collaborators. The integrations are strictly opt-in and not live-verified.

## Quickstart (Windows PowerShell)

Requirements: Windows 10/11, Python 3.12 or 3.13; optional WSL2 for external runtimes. No Docker required for the tested foundation.

```powershell
git clone https://github.com/brutalstein/jarvis.git
cd jarvis
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[api,integrations,dev]"
python -m pytest -q
$env:JARVIS_OPERATOR_TOKEN = python -m jarvis new-token
python -m jarvis serve
```

Another terminal:

```powershell
$headers = @{ Authorization = "Bearer $env:JARVIS_OPERATOR_TOKEN" }
$task = Invoke-RestMethod -Uri http://127.0.0.1:8765/v1/tasks -Method Post -Headers $headers -ContentType 'application/json' -Body '{"objective":"hello jarvis"}'
Invoke-RestMethod -Uri "http://127.0.0.1:8765/v1/tasks/$($task.id)/run-echo" -Method Post -Headers $headers -ContentType 'application/json' -Body '{}'
```

The built-in **echo** executor is deterministic and demonstrates the complete task→action→evidence chain; it is **not** a model. Real external agents require authentication, safe runtime isolation, their own tests and independent effect verification. `python -m jarvis --db jarvis.sqlite3 create "Hello"` and `python -m jarvis --db jarvis.sqlite3 get ID` work without the HTTP server. Only one backend process should write to the same SQLite file in v0.1.

## Operator approval

High/critical tasks enter `WAITING_FOR_APPROVAL`. The API can create a proposal (`POST /v1/tasks/{id}/approval-request`) but **cannot grant** it. A trusted operator must grant out-of-band from the server machine:

```powershell
python -m jarvis approve-grant APPROVAL_ID --confirm APPROVAL_ID
```

The associated exact-action digest, task ID, expiry and single-use restriction are checked before execution. This prototype assumes a trusted local OS operator; an attacker with access to the OS account can still bypass the process. Don't grant external effects until secure sandboxing is installed.

## What actually works

- Python stdlib SQLite task/event store, transactionally enforced state graph, process-restart ambiguity quarantine.
- Idempotent task admission and action-intent deduplication, cooperative single-host leases, DAG dependency gating.
- Capability policy and out-of-band manual approval; immutable canonical action digest with expiration and one use.
- Deterministic provider routing registry (selection policy only; **not** provider connectivity).
- Token-authenticated loopback-only FastAPI developer API and CLI, evidence-gated local echo workflow.
- Optional read-only n8n API and read-only OpenClaw Gateway protocol clients; optional standalone Browser Use and Gemini CLI adapters. **These are code paths only, not tested against running instances.**

## Not yet working

No real OpenClaw agent execution, n8n→OpenClaw round trip, end-to-end browser account action, secure coding workspace, Postgres/multi-host queue, live Claude/Codex harness integration, user-visible approval UI, distributed tracing, or full cancellation. Do not connect high-privilege external runtimes until these gaps are resolved. See [limitations](docs/LIMITATIONS.md), [security](docs/THREAT_MODEL.md), [research](docs/RESEARCH_AND_COMPATIBILITY.md), and [engineering review](docs/ENGINEERING_REVIEW.md).

## Design intent

**Models propose. Policies authorize. Executors act. Evidence verifies. JARVIS Core records.** No UI code is included. Authentication credentials are provided by environment variables and are never committed.


## Core hardening update

See [Core hardening](docs/CORE_HARDENING.md) for enforced routing, lease, verified-action completion, and orphaned-intent recovery. All external integrations remain opt-in and not live-verified.
