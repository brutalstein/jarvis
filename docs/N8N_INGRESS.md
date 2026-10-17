# n8n → JARVIS Core: bounded proof workflow

This milestone implements a real HTTP ingress contract backed by the existing task engine, action authorization, SQLite journal, deterministic executor and verified result. **It does not execute OpenClaw agents, Browser Use actions or arbitrary workflow tools.** Only local, side-effect-free echo is allowed.

Official background: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/ and https://docs.n8n.io/workflows/expressions/

## Trust boundary

- JARVIS Core's main operator bearer credential is never shared with n8n.
- The integration requires `JARVIS_N8N_INGEST_TOKEN` (at least 32 chars) and an explicit `JARVIS_N8N_WORKFLOW_IDS` comma-separated allowlist.
- Use n8n's HTTP Request node with `POST http://127.0.0.1:8765/v1/integrations/n8n/echo` and a secret Header Auth credential named `X-Jarvis-N8n-Token`.
- Send a JSON body with three fields: `{"workflow_id":"WORKFLOW_ID","execution_id":"EXECUTION_ID","objective":"safe example"}`.
- Map the two identifiers using n8n's workflow/execution expressions, and ensure they are the actual recorded IDs (not invented request input).
- Each (workflow_id, execution_id) is an idempotency identity, not a general-purpose replay-resistant signature. Changed payload with an existing identity is rejected with 409.
- The same identity and payload returns the same task ID. Only one worker can acquire its task. The endpoint cannot access agent tools, promote code, send email, write files, or approve an external effect.
- A new, authorized workflow execution is allowed to create its own bounded echo task. Protect and restrict n8n itself.
- Responses: 200 `COMPLETED` with verified echo output, 202 if another delivery is still processing, 401/403 for authorization failure, and 409 on conflicting replays or tasks requiring reconciliation.

## Run locally

Start the Core API with a separate operator token. Generate a new random n8n token:

`python -m jarvis new-token`

Place it in `JARVIS_N8N_INGEST_TOKEN` and the real workflow ID in `JARVIS_N8N_WORKFLOW_IDS`, then restart the API.
Configure the n8n HTTP Request node's header credential and JSON input. Never store the secret inside committed workflow JSON.

If n8n is in WSL2 or Docker and the Core is bound to Windows loopback, `127.0.0.1` from inside the container is **not** the Windows host. For this first milestone use a same-host loopback deployment or a deliberately authenticated and tightly restricted proxy. Do not expose the API to a public interface to make Docker connectivity work.

## Verification evidence and limitations

Offline FastAPI integration tests exercise actual HTTP requests through the task, policy, persistence and verifier, including failure, replay and missing token cases. This is **not** a test against a running n8n service. Separate opt-in live tests and a packaged workflow export remain outstanding.

The first proof workflow is intentionally synchronous, bounded and side-effect-free. General-purpose automation needs a separately reviewed action registry, independent verification and external reconciliation before it can be enabled.
