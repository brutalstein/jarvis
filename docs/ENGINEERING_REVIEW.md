# Adversarial review and evidence — 2026-10-17

| Perspective | Finding | Disposition |
|---|---|---|
| Architecture | No competing global orchestrator in code; adapters are optional and not invoked by engine | Accepted limited scope |
| Distributed systems | SQLite leases do not solve external exactly-once delivery or cross-host ownership | Explicitly unsupported; P0 before scale |
| Security | Out-of-band manual CLI grants eliminate automatic approval from same bearer HTTP surface | Implemented + tested; OS identity not cryptographically bound |
| Agent reliability | Task restart quarantine prevents blind replay of uncertain effects | Implemented + unit-tested; reconciliation adapters missing |
| Performance | All operations are local and bounded in task size; no substantive stress data yet | Baseline pending |
| Windows | Python 3.12+ and PowerShell setup documented; Windows runner CI configured | Not independently verified on Windows yet |
| Maintainability | Small cohesive core and optional adapters; schema has no versioned migrations yet | Migration milestone |

Evidence: `python -m pytest -q` runs 22 local deterministic tests for state invariants, authorization, approvals, idempotency, leases, dependencies, restart recovery and routing. Individual optional clients are **not** evidence of real service integration. No production-ready claim is made.

Acceptance coverage: state machine **partial**; policy **partial**; task persistence **verified locally**; browser execution **not live-verified**; n8n automation **not implemented end-to-end**; OpenClaw agent execution **not implemented**; Claude/Codex **not implemented**; Gemini adapter **implemented not live verified**; multitenancy **out of scope**; independent external verification **not implemented**.
