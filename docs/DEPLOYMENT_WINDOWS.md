# Windows local deployment

1. Install a supported Python 3.12+ distribution. Use PowerShell and `py -3.12 -m venv .venv`.
2. Activate `.venv`, install `pip install -e ".[api,integrations,dev]"`, run `python -m pytest -q`.
3. Generate an operator token: `python -m jarvis new-token`; store privately in `$env:JARVIS_OPERATOR_TOKEN` for the session; never commit it.
4. Start with `python -m jarvis serve`; API bound to `127.0.0.1:8765`, no public exposure.
5. Stop using Ctrl+C. Inspect task status after restart; interrupted RUNNING/VERIFYING tasks will be quarantined automatically.
6. Back up `jarvis.sqlite3` using SQLite's online backup API or while the application is stopped; never copy a live WAL DB without its companion WAL state.

Optional OpenClaw and n8n should run on WSL2/Docker with explicit host-to-loopback isolation; adapter connectivity is *not* proof of safe agent execution. Browser Use installation (Python 3.12 runtime, browser install) follows official Browser Use docs and is opt-in.
