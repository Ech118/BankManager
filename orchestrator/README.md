# orchestrator/ — P3

**Owner: P3.** Rules: [docs/p3/CLAUDE.md](../docs/p3/CLAUDE.md).
Pipeline: [docs/pipeline.md](../docs/pipeline.md).

## Public interface

```python
run_analysis(ticker, as_of=None, redact=None) -> Verdict
```

Plus HTTP, in `server.py`:

```
POST /api/analyze              {"ticker": "ACME"} -> {"run_id"}
GET  /api/runs/{id}/events     SSE {"agent","status","ts"}
GET  /api/runs/{id}            the Verdict when finished
```

## Layout

```
coordinator.py   plan, spawn, collect, route retries
mcp_client.py    the ONLY door to data (in-memory transport / stdio)
retry.py         targeted retry execution, capped at 2
server.py        FastAPI + SSE
events.py        per-agent progress events, and token accounting
report/          deterministic Verdict rendering from ResearchState
```

## Three things that are easy to get wrong

**Parallelism.** `financial` and `business` are independent and must actually
run concurrently. Otherwise wall-clock is the sum rather than the max, and the
per-agent UI lanes have nothing interesting to show.

**The redact hook.** Applied centrally, to all filing text, before any agent
call. If each agent applied it, an agent fetching its own section text could
bypass anonymization and quietly contaminate a backtest.

**The Red Team's input.** It gets the raw fact sheet, not just the other agents'
summaries — otherwise it produces agreement in a sceptical tone.

## The boundary

P3 imports neither `data/` nor `calc/`. Everything arrives through
`mcp_client.py`, which speaks real MCP in **both** modes — the SDK's in-memory
transport for mock and tests, stdio for live. Shortcutting to `data.api` in mock
mode would mean the wiring was only ever exercised in production.

## Reports are generated, not written

`report/` renders a `Verdict` from a `ResearchState` deterministically. No LLM
runs there. Agents produce `Claim`s; only `Claim`s get rendered — which is what
keeps unverified prose away from the reader
([ADR 0004](../docs/adr/0004-report-rendered-from-research-state.md)).
