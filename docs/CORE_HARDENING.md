# JARVIS Core security and consistency hardening

This change addresses previously demonstrated gaps without asserting production readiness.

## New enforced invariants

1. Provider routing requires a matching declared operation; authentication and health must both be true.
2. A worker with an active lease cannot have its task mutated by an unowned caller.
3. COMPLETED requires a matching verified action record and exact persisted verifier evidence, not caller-written flags alone.
4. On restart, both interrupted active tasks and nonterminal tasks with unclosed action intents are quarantined to RECOVERY_REQUIRED.
5. Lease admission failure after an action was recorded is explicitly quarantined, not left READY.

These guarantees are confined to the local SQLite core; no OS sandbox or external exactly-once effect is implied.

## Remaining P0 work

- Introduce securely sandboxed real OpenClaw agent dispatch, independent verifier contracts and live compatibility tests.
- Complete n8n webhook and Browser Use round trips with authorization and no bypass paths.
- Replace ad hoc operator identity with device-backed approval authentication.
- Design external effect reconciliation and local secret management.
- Carry out end-to-end Windows integration testing against real installed services.

## Verification

Run `python -m pytest -q`, `python -m compileall -q jarvis services`, and `python -m ruff check jarvis services tests --select E4,E7,E9,F`. GitHub Actions tests Python 3.12 and 3.13 on Windows and Ubuntu. These are not live provider tests.

6. Low-risk actions acquire a worker lease before a side-effect intent is recorded. Abandoned READY leases are quarantined on restart.
7. RECOVERY_REQUIRED tasks with an unresolved action cannot be made READY without explicit reconciliation.
8. OpenClaw Gateway read-only access now checks protocol and granted scopes from the actual hello-ok response.
9. CI uses the current GitHub-maintained Node 24+ based checkout/setup-python actions.
