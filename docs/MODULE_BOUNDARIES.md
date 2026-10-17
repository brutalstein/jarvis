# JARVIS Core: module boundaries

The local backend is a **modular monolith**, not a network of competing orchestrators.
Each operation has exactly one task/authorization authority. These boundaries are
enforced by tests and should be maintained when adding providers.

```text
jarvis/
  domain/         contracts.py · routing.py       [task semantics; pure Python]
  application/    engine.py · policy.py           [business execution authority]
  persistence/    sqlite.py                       [durable single-host SQLite]
  integrations/   openclaw.py · n8n.py · gemini.py
                  process.py · errors.py          [external clients; no autonomy]
  entrypoints/    http.py · n8n_ingress.py · cli.py                [delivery/transport boundary]
  *.py            legacy import facades           [no second implementation]
```

## Explicit dependency rules

| Package | Can depend on | Must NOT depend on |
|---|---|---|
| domain | domain, stdlib | application, persistence, integrations, entrypoints |
| application | domain, application | integrations, entrypoints |
| persistence | domain, persistence | application, integrations, entrypoints |
| integrations | domain, integrations | application, persistence, entrypoints |
| entrypoints | domain, application, persistence, integrations | no other business authority |

Application policy and task engine now depend on the runtime-checkable `TaskRepository`
protocol. SQLite implements approval/action journaling atomically behind that port;
future PostgreSQL support must implement the **same transaction semantics** rather
than creating parallel approval state or weakening replay protection.

Use canonical imports in new code: `jarvis.domain.*`, `jarvis.application.*`,
`jarvis.persistence.*`, `jarvis.integrations.*`, and `jarvis.entrypoints.*`.
The root `jarvis.engine`, `jarvis.storage`, `jarvis.adapters`, etc. remain *thin
compatibility facades* and must not accumulate new behavior.

New providers get one focused adapter module; approval remains owned by application,
and n8n/Gateway clients cannot independently authorize external effects.
No second task state machine, global scheduler or model orchestrator may be added.

## Verification and limits

`tests/test_architecture.py` verifies the dependency graph, canonical import identity
and thin facade boundaries. All original HTTP endpoints and CLI commands remain supported.
This does not add an operating-system sandbox, real Claude/Codex sessions, or live
n8n/Browser Use verification; these remain P0 prerequisites for privileged autonomy.
