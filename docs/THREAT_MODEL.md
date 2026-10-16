# Threat model (v0.1)

Trust boundary: authenticated human-operated loopback API; untrusted task objective, repo/web text and model output; no external execution enabled by default. Assets: task DB, approval records, credentials, local filesystem, n8n/OpenClaw sessions, private browsing content.

| Threat | Current mitigation | Remaining severity |
|---|---|---|
| Prompt injection and tool-output manipulation | No LLM output accepted as authorization or completion proof | High until independent sandboxed tool gate exists |
| Credential exfiltration | Secrets kept out of repository; local operator token; n8n client uses header, no URL embedded credentials | High until secret manager, trace redaction and outbound allowlists |
| Unauthorized HTTP call | Token comparison and loopback binding | Medium; no rate limiter/TLS, local malware shares host |
| Forged approval | Exact action hash, expiry, operator CLI-only grant, consumed flag | High; same OS operator account is trusted |
| Duplicate webhook and action | UNIQUE idempotency key and action digest; transactions | High for unintegrated external systems (no end-to-end dedupe yet) |
| Worker crash during effect | Move running/verifying to RECOVERY_REQUIRED on restart | High; cannot prove external outcome without reconciliation adapter |
| Race/lease contention | Serialized `BEGIN IMMEDIATE`, lease acquisition conditional on READY | Medium; SQLite single-host only, owner identity isn't a security credential |
| Path traversal/symlink escape | No arbitrary file operation exposed over API | High when coding agents become enabled |
| Untrusted dependencies | Minimal stdlib required deps; external optional | Medium; lock/SBOM/scanning pending |
| Service compromise, lateral movement | Loopback-only design, no privileged service access by default | High without real VM/container isolation |
| Browser session leakage | One-shot design; no browser endpoint available by default | High; real profile isolation untested |
| Dangerous CLI tools | CLI integrations not called from central executor | High if future adapter enabled without sandbox |
| Unbounded resource use | Per-process timeout, concurrency gate on echo, task-size limit | High; quotas/backpressure/output streaming not fully enforced |

Never expose n8n admin, OpenClaw Gateway, DB port or JARVIS API to public ingress. Treat local runtime access as a privileged operation. Operator must audit capabilities and external effects before any broader deployment.
