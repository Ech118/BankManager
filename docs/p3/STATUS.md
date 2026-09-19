# P3 status

Update whenever a capability moves from mock to real, or when blocked.
A PR that changes behaviour must update this file.

**Step:** 2 backend built (offline-verified). **Next:** finish Step 2's `web/` UI, then Step 3 (Business Agent, parallelism, SSE lanes).
**Blockers:** the real mock MCP server (P1) - see
[the request](../requests/2026-09-19-p3-to-p1-mock-mcp-server.md) - and where the report's inputs and the auditor's Factsheet come
from - see [the report-inputs request](../requests/2026-09-19-p3-report-inputs.md). Everything up to that seam is tested against a
P3-owned MCP test double (`tests/e2e/support/fake_mcp.py`).

| Capability | State | Notes |
|---|---|---|
| `run_analysis` (`orchestrator/api.py`) | mock | still returns the ACME verdict fixture; signature unchanged. Wire it to the Coordinator once a server exists and the report generator (Step 2) can render a Verdict. |
| Coordinator | **Step 2 built** | `run_state()`: ingest via MCP -> financial agent -> (optional) verify -> validated `ResearchState`, with `company_name` and `market` stored on it. Sequential. `run()` raises `NotImplementedError` (Step 5). |
| Verifier wiring (`verify()`) | **built, tested with a stub auditor** | one pass; marks claims `verified`/`failed`; auditor and factsheet are **injected** (P3 can't import `audit/` or `data/`). Retry loop is Step 5. |
| MCP client (in-memory) | **built, tested** | real MCP SDK session; args validated against `TOOL_REQUESTS`, responses against `TOOL_RESPONSES`; server is **injected** (P3 may not import `mcp_server/`) |
| MCP client (stdio) | **built, tested** | spawns any server command; tested against the test double as a subprocess |
| `agents/base.py` | **built, tested** | shared rules + role prompt, untrusted-text fence, verbatim-quote enforcement, fact_id -> ValueObject, retry once then fail loudly, `to_claims` |
| Financial Agent | **built (mock LLM)** | live Anthropic path written in `agents/client.py`, **never run against the API** (no key here) |
| Business, Valuation, Scenario, Red Team, Synthesizer | stub | Steps 3-5 |
| Parallel execution | not started | Step 3 |
| Retry loop (`retry.py`) | not started | Step 5 |
| Report generator (`orchestrator/report/`) | **built, tested** | deterministic Jinja render: card first, case against, sections; unverified claims marked, pending claims marked `unchecked`, `unavailable` never 0, fact/estimate/assumption carried, disclaimer top and bottom. Without a synthesizer it renders a PRELIMINARY report with no card. `render()` needs `state.synthesis` (`agents/synthesis.py`) and raises `ReportInputError` rather than invent it. |
| FastAPI server + SSE | **built, tested** | `POST /api/analyze`, `GET /api/runs/{id}`, `/events` (SSE, full replay for late subscribers), `/stats`, `/config`. Runner is injectable (`server.RUNNER`). |
| `web/` UI | in progress | Step 2; types and API client drafted by Step 0 |
| Prompt-injection guard | **built, tested** | instruction-like sentences removed before the model sees them and reported in `data_quality.gaps`. The full "verdict must not move" e2e test needs the Synthesizer (Step 5). |
| Redact hook | **built, tested** | applied in `Agent.wrap_untrusted`, i.e. before every model call; `ResearchState.redacted` recorded |
| Cost/latency logging | partial | tokens/seconds per agent in `Coordinator.stats` and `orchestrator/logs/runs.jsonl` (gitignored). Rates in `agents/client.py::PRICES` are an ASSUMPTION copied from the claude-api skill (2026-06-24). |

## Design decisions worth knowing
- **The model never types numbers.** It cites `fact_id`s; `agents/base.py` builds each ValueObject from the fact row.
  A finding whose number has no fact id never becomes a Claim.
- **A fabricated quote is dropped exactly like a missing one**: evidence must appear verbatim (whitespace-normalised)
  in a document *this agent was actually shown*, after redaction and injection removal.
- **No documents at all -> empty analysis, not a crash** (e.g. `as_of` before any filing). The coordinator records the gap.
- **Models:** `claude-sonnet-5` for most agents, Haiku for the verifier (Step 0's `MODEL_BY_AGENT`); `BM_MODEL` overrides.
- Agents receive context pre-fetched by the coordinator through MCP. A tool-use loop (agents calling MCP themselves) is
  a later step; `Agent.tools` already declares each agent's allowed set.

## Known gaps
- The mock `ResearchState` has no synthesizer output, so the Step 2 checkpoint test composes `synthesis`/`market`/`company_name` from the other fixtures. See the report-inputs request.
- `fixtures/mock/analysis_financial.json` cites facts missing from `facts.json` (`gross_profit`, `receivables`, `sbc`
  FY2025); the agent ignores unknown fact ids and logs it. Coordinator follow-up: extend the facts fixture.
- v1 P3 work (forensic/business/balance-sheet/valuation/red-team/synthesizer against the v1 contracts) is preserved on
  branch `p3-v1-backup`; its injection test with a control run should be ported at Step 5.

## Run / test (from repo root)
```
python -m pytest agents/tests orchestrator/tests tests/e2e -q
make lint && make test-contracts
uvicorn orchestrator.server:app --port 8000
```

**Last updated:** 2026-09-19 (Step 2 backend)
