# P3 status (Agents, Orchestrator & Web)

Updated by the P3 owner whenever a capability moves from mock to real, or when blocked.

| Capability | State | Notes |
|------------|-------|-------|
| `orchestrator.api.run_analysis` pipeline | **real code, runs in mock** | scope -> factsheet -> metrics -> scout -> 3 analysts in parallel -> valuation -> `calc.evaluate_scenarios` -> red team -> synthesizer -> audit -> verdict. Depends on P1/P2 `api.py`; works today against their ACME stubs. |
| Prompts (`prompts/*.md`) | done | one file per agent + `_shared.md` (data-not-instructions, quote+source_id, numbers by reference) |
| Agents (`agents/`) | done (mock-tested) | forensic, business (incl. management), balance_sheet, valuation, red_team, synthesizer. Scout is deterministic (no LLM). |
| Live LLM (`agents/llm.py` AnthropicLLM) | **written, NOT run against the API** | no `ANTHROPIC_API_KEY` in this environment. Uses `anthropic` SDK, structured JSON output, adaptive thinking, streaming, prompt caching, optional server-side refusal fallback. First live run may need small fixes. |
| FastAPI server + SSE (`orchestrator/server.py`) | done | POST /api/analyze, GET /api/runs/{id}, /events (SSE, replay for late subscribers), /stats, /config |
| Injection guard | done + tested | sentence-level removal, `<document>` fencing, reported in `verdict.data_quality.gaps` |
| Redact hook | done + tested | applied before agents AND to the auditor's text getter |
| Cost/latency log | done | per agent tokens, seconds, est. $ in `GET /api/runs/{id}/stats` and `orchestrator/logs/runs.jsonl` (gitignored). $ rates are an ASSUMPTION copied from the claude-api skill (2026-06-24). |
| Web UI (`web/`) | see below | |
| e2e tests | mock done | live thin slice waits for P1/P2 live (Checkpoint 3) |

## Design decisions worth knowing
- **LLM never types numbers.** Agents return `number_refs` (paths into the fact sheet / metrics / scenario_result); the pipeline resolves them to the real value objects. Card numbers (scores, P(beat S&P), expected return, price, market cap) are inserted by code.
- **Findings without a verbatim quote are dropped** and logged; if none survive the agent is retried once, then the run fails loudly.
- **Valuation emits `analysis` + `scenarios`** in one call (plan said "scenarios only": it still never emits scores or P(beat)). Code re-checks its `eps_at_horizon` against its own drivers (15% tolerance) and re-prompts once on mismatch.
- **Models:** default `claude-opus-5` for analysts (claude-api skill default), `claude-haiku-4-5` reserved for the "light" tier (unused today because Scout is deterministic). Override with `BM_MODEL_ANALYST` / `BM_MODEL_LIGHT`; `BM_EFFORT` sets effort.
- Section 12 of plan.txt (MCP) untouched; P3 does not use MCP: agents receive documents pre-fetched via `data.api`.

## Run / test (from repo root)
```
python3 -m pytest agents/tests orchestrator/tests tests/e2e -q      # P3 tests
make check-contracts                                                # frozen contract tests
uvicorn orchestrator.server:app --port 8000                         # API (mock by default)
```

Last updated: 2026-09-19
