# Architecture and ownership — 2026-10-17

| Component | Sole owner of | Allowed delegation |
|---|---|---|
| JARVIS Core | Task state, policy, approvals, budgets, side-effect intent, correlation IDs and verification | Executes bounded requests through adapters |
| OpenClaw | Agent runtime, sessions, agent-local context | Only capabilities admitted by JARVIS; **not yet enforced across OpenClaw tool chains** |
| Browser Use | Isolated browser session and navigation | Only explicit browser jobs; **no secure local containment yet** |
| n8n | Workflow schedules/triggers and internal workflow retries | Submit task through authenticated JARVIS API |
| Claude, Codex, Gemini | Proposals, planning and coding assistance | No independent global task writes or promotion to privileged tools |

Current call graph: `CLI/HTTP -> Engine -> Store + ActionGate -> builtin.echo -> evidence -> Store`.

Future execution graph: `n8n webhook / CLI -> admission -> planning proposals -> deterministic provider selection -> capability gate -> sandboxed agent/browser/n8n execution -> external read-after-write verification -> authoritative event log`.

The task DB is **not** shared with OpenClaw or n8n. Agents never receive the SQLite path or operator token. Approved actions are hashed over kind, exact parameters, capability, risk and task ID. This prevents approval reuse after a material action change.

## Deployment scope

Single trusted Windows operator; loopback HTTP; single SQLite host; Python 3.12/3.13 tested on Linux sandbox; optional external runtime processes. Distributed claims and unverified adapters are deliberately disabled by default.

## ADR-001 — Python stdlib foundation instead of premature multi-service stack

The user directive *prefers* strict TypeScript + PostgreSQL but explicitly allows an engineering alternative. Under the current offline build environment, a compact Python runtime and SQLite enables executable durability and security tests without claiming a TypeScript/Postgres stack was tested. PostgreSQL migration and typed contracts are the next milestone. Never treat SQLite leases as cross-host guarantees.

## ADR-002 — External agents behind offline-only adapters

There are no live credentials, Docker daemon, OpenClaw Gateway, installed Browser Use worker or provider CLIs in the validation environment. Optional adapters expose bounded read-only capabilities but the central engine does not route autonomous side effects to them. Integration activation requires an explicit security/reliability milestone and actual live test evidence.

## Verified echo workflow ingress increment

The n8n ingress uses a dedicated credential that cannot authorize the operator API. The route admits only low-risk, side-effect-free echo tasks. Its authoritative state and idempotency records reside in the same Core SQLite store as ordinary developer tasks. The template workflow does not confer global agent dispatch authority; any upgrade requires a separately reviewed action gateway and live-service verification.
