# Official-source research and compatibility record

Research date: 2026-10-17. Sources were reviewed on the public official docs. A documentation page listing a release is **not** the same as testing that release. Exact versions for uninstalled dependencies are not claimed validated. Base foundation: Python 3.13.5 locally verified, Python >=3.12 declared, SQLite through stdlib.

| System | Official verified contract | Repository integration decision | Live verified? |
|---|---|---|---|
| OpenClaw | [Gateway protocol](https://docs.openclaw.ai/gateway/protocol), [handshake](https://docs.openclaw.ai/gateway/protocol/handshake), [trusted client](https://docs.openclaw.ai/gateway/clients) | Loopback token-authenticated v4 `gateway-client`/`backend`, read-only RPC allowlist; `@openclaw/gateway-client` official JS SDK should replace Python wire code when TS migration occurs | No |
| Browser Use | [official quickstart](https://docs.browser-use.com/open-source/quickstart) shows `Agent(task=..., llm=ChatBrowserUse())` + `run()` | Isolated one-shot Python worker module; not permitted to execute automatically from Core | No |
| n8n | [Public API authentication](https://docs.n8n.io/connect/n8n-api/authentication) specifies `X-N8N-API-KEY`; API rooted at `/api/v1` | HTTPS or loopback GET workflows read client; real webhook round-trip remains pending | No |
| Claude Code | [Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview) | Preferred official SDK; adapter not yet implemented | No |
| Codex | [SDK](https://developers.openai.com/codex/sdk/) | Prefer official SDK/harness over inventing executable arguments; adapter not yet implemented | No |
| Gemini CLI | [Headless mode](https://geminicli.com/docs/cli/headless/) supports `--prompt` and `--output-format json` | Optional process adapter validates `response` and exit code; **not in Core executor path** until tool isolation is established | No |

OpenClaw official docs reference Gateway npm `2026.8.1` packages, while the OpenClaw docs release navigation lists later core releases (v2026.10.4): package/wire and core releases must be checked separately before integration. The Python handshake assumes protocol v4 and must be contract-tested against the actual installed Gateway. Latest stable release of every listed runtime was **not comprehensively established**; do not auto-upgrade, pin reviewed deployment versions before enabling live integration.

Provider subscription authentication and API authorization are different; never assume the presence of a ChatGPT/Claude/Gemini subscription grants server SDK usage. No external credentials or service instances were supplied for validation.
