# Importable n8n workflow proof

The file `examples/n8n/verified-echo.json` contains a manual-trigger n8n workflow with a typed HTTP Request node. It intentionally includes no credential IDs or tokens.

1. Import the workflow JSON into a trusted self-hosted n8n instance.
2. Save the workflow. Copy its resulting **actual workflow ID**.
3. Set `JARVIS_N8N_WORKFLOW_IDS` to that exact ID on Core, and configure a new dedicated `JARVIS_N8N_INGEST_TOKEN` (>=32 characters). Restart Core.
4. In n8n create a **Header Auth** credential: Header Name `X-Jarvis-N8n-Token`, Header Value = the generated integration token.
5. Open the imported HTTP Request node and select that credential. Do not put the token in a node parameter.
6. Run with a manual execution while n8n and Core share the same loopback host. The node should return a completed, verified echo task. A copied execution ID and identical objective are idempotent.
7. For Docker/WSL2, `127.0.0.1` is container-local: arrange an authenticated, explicitly restricted route to the Core process. Do not remove Core's loopback-only default to make the example work.

The exported workflow is a configuration template, **not** proof of a running live n8n integration. The corresponding API-level tests validate the Core side only.
