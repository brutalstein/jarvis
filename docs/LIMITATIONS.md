# Limitations and unresolved milestones — 2026-10-17

**P0 before production:** isolated OS-level tool execution; no bypass path from agent to privileged OS/network; external side-effect reconciliation; manual approval bound to trusted identity and device; secure secrets; local ingress hardening; resource quotas; real OpenClaw agent lifecycle verification; persistent PostgreSQL workers if multi-host.

**P1:** provider-specific verified cancel semantics; n8n authenticated webhook replay defenses and real workflows; Browser Use session cleanup/verification; Claude/Codex official SDK adapters; Gemini read-only capability guarantees; schema migrations; OpenTelemetry; application-level model budgets; Windows native/WSL2 tests; dependency lock and CVE scan.

**P2:** full DAG cycle detection for adding edges after creation (current interface only creates a fresh node and accepts existing parents), statistically meaningful routing telemetry, structured provenance and long-term memory, UI/voice and remote workers.

The v0.1 SQLite store is intended for **one process / one host**, not multi-host exactly-once execution. The `BEGIN IMMEDIATE` transaction and action UNIQUE key govern only DB admission; they cannot guarantee an irreversible external side effect happens once. Cancellation of actively running work is rejected rather than falsely marked complete. The echo executor verifies only exact output equality, not semantic validity of arbitrary objectives.

**Integration status:** All live OpenClaw/n8n/BrowserUse/Claude/Codex/Gemini E2E validation blocked by missing configured runtimes, credentials, and external services; any mock or local-only test is labeled as such. No cross-platform CI results until GitHub Actions completes.
