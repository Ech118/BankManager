# P3 HTTP API

Served by `orchestrator/server.py`. `docs/pipeline.md` names three endpoints; this is the full set P3 actually serves.
Ticker input is validated against the contract pattern before any work starts (error F).

| Method + path | Returns |
|---|---|
| `POST /api/analyze` `{"ticker": "ACME", "as_of": null}` | `{"run_id"}`. `422` for a malformed ticker or date. Tickers are upper-cased. |
| `GET /api/runs/{id}` | `200` the **Verdict**; `202 {"status":"running"}`; `409 {"status":"preliminary"}` when the run gathered evidence but has no verdict yet (Steps 3-4); `422 {"status":"failed","error"}` with the reason (for example an out-of-scope bank); `404` unknown run. |
| `GET /api/runs/{id}/report` | For a preliminary run: `{"markdown", "state", "stats"}`. `404` otherwise. |
| `GET /api/runs/{id}/events` | Server-Sent Events, one JSON object per state change: `{"run_id","agent","status","ts","detail?","tokens_in?","tokens_out?"}`. `agent` is a roster agent or a stage (`ingest`, `verify`, `guard`, `run`). `status` is `running`, `retrying`, `done`, `failed` or `flagged`. Full history is replayed to late subscribers; the stream ends when the run does. |
| `GET /api/runs/{id}/stats` | Tokens, seconds and per-agent breakdown for the run. |
| `GET /api/config` | `{"mode","llm"}` so the UI can show a mock banner. |
| `GET /api/health` | `{"ok": true}` |

**CORS.** Allowed origins are `http://localhost:3000` and `http://127.0.0.1:3000` by default. Set
`BM_CORS_ORIGINS="https://a.example,https://b.example"` to override. `*` is refused: the API starts model runs that cost money.

**Composition.** P3 may not import `mcp_server/` or `audit/`, so whoever runs the server injects them:

```python
from orchestrator import server
server.configure(mcp_factory, auditor=run_audit, factsheet=provider, verify_claim=make_verify_claim())
app = server.create_app()          # uvicorn ...:app
```

`tests/e2e/support/dev_app.py` is the demo composition over the MCP test double.
