# P3 — Agents, orchestrator & web

**Owns:** `agents/`, `prompts/`, `orchestrator/`, `web/`, `tests/e2e/`,
`docs/p3/`
**Branch:** `p3-agents`
**Produces:** analyses, the verdict, and the UI
**Default coordinator** — applies approved contract changes and runs the
checkpoints

## Scope

- `agents/` — six agents and their tool wiring
- `prompts/` — one prompt per agent, plus the shared rules
- `orchestrator/` — coordinator, MCP client, retry execution, FastAPI + SSE
- `orchestrator/report/` — deterministic rendering from `ResearchState`
- `web/` — Next.js UI
- `tests/e2e/` — the checkpoint tests

## Public interface

`orchestrator/api.py`:

```python
run_analysis(ticker, as_of=None, redact=None) -> Verdict
```

Plus HTTP: `POST /api/analyze`, `GET /api/runs/{id}/events` (SSE),
`GET /api/runs/{id}`.

## Dependencies

`schema.contracts` only. **P3 imports neither `data/` nor `calc/`** — everything
arrives through MCP tools ([ADR 0007](../adr/0007-partition-boundaries.md)).

## The heaviest partition

P3 owns the most surface area. `web/` is fully mock-driven so it can be
reassigned if P3 falls behind — keep it that way.

## Three things that are easy to get wrong

1. **Parallelism.** `financial` and `business` must actually run concurrently.
2. **The redact hook.** Applied centrally, before any agent call. Per-agent
   application lets an agent fetch un-redacted text and contaminate a backtest.
3. **The Red Team's input.** It gets the raw fact sheet, not the other agents'
   summaries — otherwise it produces agreement in a sceptical tone.

## Done when

- Mock and live thin slices produce a schema-valid verdict that passes audit
- The UI renders it, with the disclaimer on every page
- The prompt-injection test passes
- Per-run cost and latency are recorded
