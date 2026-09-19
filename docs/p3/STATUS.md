# P3 status

Update whenever a capability moves from mock to real, or when blocked.
A PR that changes behaviour must update this file.

**Step:** 4 built offline (Valuation Agent; three agents, three stages). **Blocked from finishing the live checkpoints** (Steps 3 and 4) by P1's MCP server, live data, P2's real `calc/`, and an API key. **Next:** Step 5 (Scenario Agent, Red Team, Synthesizer) needs `calc.evaluate_scenarios` (P2); see [TO_BE_FIXED.md](TO_BE_FIXED.md).
**Blockers:** the real mock MCP server (P1) - see
[the request](../requests/2026-09-19-p3-to-p1-mock-mcp-server.md) - and where the report's inputs and the auditor's Factsheet come
from - see [the report-inputs request](../requests/2026-09-19-p3-report-inputs.md). Everything up to that seam is tested against a
P3-owned MCP test double (`tests/e2e/support/fake_mcp.py`).

| Capability | State | Notes |
|---|---|---|
| `run_analysis` (`orchestrator/api.py`) | mock | still returns the ACME verdict fixture; signature unchanged. Wire it to the Coordinator once a server exists and the report generator (Step 2) can render a Verdict. |
| Coordinator | **Step 2 built** | `run_state()`: ingest via MCP -> financial agent -> (optional) verify -> validated `ResearchState`, with `company_name` and `market` stored on it. Sequential. `run()` raises `NotImplementedError` (Step 5). |
| Verifier wiring (`verify()`) | **built, tested with a stub auditor** | audit -> targeted retries -> re-audit -> mark; auditor, factsheet and `verify_claim` are **injected** (P3 can't import `audit/` or `data/`). |
| Retry loop (`orchestrator/retry.py`) | **built, tested** | executes `retries_issued`: re-runs ONE agent for ONE section with the gate's reasons, max 2, then claims ship `unverified` with a visible marker. Never drops a claim. Contract details to confirm with P2: [request](../requests/2026-09-19-p3-to-p2-verifier-and-retry-contract.md). |
| LLM `verify_claim` (`agents/verifier.py`) | **built, tested (mock/scripted)** | fails closed; cheap model; passage sanitised and fenced; counts its own tokens. Live path never run (B8). |
| MCP client (in-memory) | **built, tested** | real MCP SDK session; args validated against `TOOL_REQUESTS`, responses against `TOOL_RESPONSES`; server is **injected** (P3 may not import `mcp_server/`) |
| MCP client (stdio) | **built, tested** | spawns any server command; tested against the test double as a subprocess |
| `agents/base.py` | **built, tested** | shared rules + role prompt, untrusted-text fence, verbatim-quote enforcement, fact_id -> ValueObject, retry once then fail loudly, `to_claims` |
| Financial Agent | **built (mock LLM)** | live Anthropic path written in `agents/client.py`, **never run against the API** (no key here) |
| Business Agent | **built (mock LLM)** | sections: company, management, competitive_position, catalysts. Reads `business`, `risk_factors`, `mdna` only. Live path never run (B8). |
| Valuation Agent | **built (mock LLM + MCP test double)** | sections: valuation, expectations. Three steps: PLAN (picks methods and peers with a reason each, from the deterministic default list) -> CALCULATE (code calls `calculate_valuation`) -> INTERPRET (findings cite calc results by path in `calc_refs` and inputs by `fact_id`). `reverse_dcf` is always computed. Numerals typed into a claim that no quote contains are dropped (the Claim contract alone would allow them beside a real fact_id). Reads the financial and business findings (`upstream_text`); the pair never see each other. Its plan and reasons are kept on the analysis as `valuation_plan`. First agent to call MCP tools itself, through an allowlist (`Agent.call_tool`). |
| Scenario, Red Team, Synthesizer | stub | Step 5 |
| Parallel execution | **built, tested** | `Coordinator.stages()`: [financial \|\| business], then [valuation]. The pair run in a `ThreadPoolExecutor`; results merged in canonical order (deterministic); a failing agent lets its partner finish, emits `failed`, and the first failure in canonical order is raised. Concurrency is proven by a two-party barrier. Neither agent sees the other's output. |
| Report generator (`orchestrator/report/`) | **built, tested** | deterministic Jinja render: card first, case against, sections; unverified claims marked, pending claims marked `unchecked`, `unavailable` never 0, fact/estimate/assumption carried, disclaimer top and bottom. Without a synthesizer it renders a PRELIMINARY report with no card. `render()` needs `state.synthesis` (`agents/synthesis.py`) and raises `ReportInputError` rather than invent it. |
| FastAPI server + SSE | **built, tested** | `POST /api/analyze`, `GET /api/runs/{id}` (verdict, or `409 preliminary`), `/report`, `/events` (SSE with a lane per agent, full replay for late subscribers), `/stats`, `/config`. `server.configure(mcp_factory, ...)` is the composition hook that puts the real Coordinator behind it. |
| Demo composition | **built** | `uvicorn tests.e2e.support.dev_app:app` = real Coordinator + server over the MCP **test double** and mock LLM, with a per-call delay so the lanes are visible. |
| `web/` UI | **built, tested (37 tests)** | Next.js: verdict card first, case against second, collapsible sections with status chips, numbers coloured by type, `unavailable` never 0, unverified/unchecked markers, data-quality banner, agent lanes, disclaimer via the site shell (every page). 31 vitest tests, typecheck, production build; screenshot-checked in Chrome. `/demo` works with no backend; `/` runs against the API and shows live lanes, then a preliminary report when there is no verdict yet (checked in Chrome: Financial and Business `running` at the same moment). `/?ticker=ACME` auto-runs. Safe markdown renderer (no raw HTML). |
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
- The UI has only been exercised against the mock verdict and the mock `run_analysis`; per-agent lanes need the Coordinator wired into the server (Step 3), so today `/` shows only `run` events.
- The disclaimer appears twice on a report page (the report's own, which must travel with the Verdict, and the site footer). Deliberate; easy to dedupe in CSS if it reads as noise.
- The mock `ResearchState` has no synthesizer output, so the Step 2 checkpoint test composes `synthesis`/`market`/`company_name` from the other fixtures. See the report-inputs request.
- `fixtures/mock/analysis_financial.json` cites facts missing from `facts.json` (`gross_profit`, `receivables`, `sbc`
  FY2025); the agent ignores unknown fact ids and logs it. Coordinator follow-up: extend the facts fixture.
- v1 P3 work (forensic/business/balance-sheet/valuation/red-team/synthesizer against the v1 contracts) is preserved on
  branch `p3-v1-backup`; its injection test with a control run should be ported at Step 5.

## Run / test (from repo root)
```
python -m pytest agents/tests orchestrator/tests tests/e2e -q
make lint && make test-contracts
cd web && npm run typecheck && npm test
uvicorn orchestrator.server:app --port 8000     # then: cd web && npm run dev
```

**Last updated:** 2026-09-19 (Step 4, offline)
