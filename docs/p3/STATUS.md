# P3 status

Update whenever a capability moves from mock to real, or when blocked.
A PR that changes behaviour must update this file.

**Step:** 5 built offline: all six agents, the full pipeline, and a finished `Verdict` in the browser. **Nothing real runs yet** because the real MCP server (P1), P2's v2 `calc/` and `audit/`, and an API key are all still missing. **Next:** whatever unblocks first; see [TO_BE_FIXED.md](TO_BE_FIXED.md).

**About P2's branch:** `origin/p2-calc` is built on the superseded v1 scaffold and cannot be merged (12 conflicts, and its `calc/metrics.py` / `calc/scenarios.py` would be silently shadowed by v2's packages). P3 did not merge it. See [the request](../requests/2026-09-20-p3-to-p2-step5-calc-contract.md).

| Capability | State | Notes |
|---|---|---|
| `run_analysis` (`orchestrator/api.py`) | mock | still returns the ACME verdict fixture; signature unchanged. `Coordinator.run()` is real (needs injected `calc`, `auditor`, `factsheet`). |
| Coordinator | **Step 5 built** | stages: [financial \|\| business] -> [valuation] -> scenario -> red team -> `calc.evaluate_scenarios` -> synthesizer (+ one consistency correction) -> verify (+ retry loop) -> `generator.render` -> `Verdict`. `calc` is an injected port. |
| Financial, Business, Valuation agents | **built (mock LLM)** | see below |
| Scenario Agent | **built (mock LLM)** | proposes bear/base/bull inputs, a REQUESTED weight per case with the reason, one prior shift. Never states P(beat), a score, a price target or an eps (`eps_at_horizon` is sent `unavailable` for calc to derive). Claims only in `scenarios`. Implausible units (8 instead of 0.08) and weights that do not sum to 1 are sent back. |
| Red Team | **built (mock LLM)** | gets the RAW facts table, filings, market snapshot and the leading view (not just summaries); returns findings, a drawdown path and an optional downward prior shift. Runs before calc so both shifts are in hand. |
| Synthesizer | **built (mock LLM)** | no filing text, no facts table; cites only pre-verified quotes; may write NO numerals; must answer every numbered Red Team point (R1, R2, ...); verdict word checked by `calc.validate_consistency` and corrected once, else the run fails. |
| Code-generated claims | **built** | `scenarios` and `sp500_comparison` claims come from calc's result (`orchestrator/scenario_claims.py`), never from a model. |
| Verifier wiring, retry loop, `verify_claim` | **built, tested** | see earlier rows; contract details to confirm with P2. |
| Report generator | **built, tested** | full render of all 14 sections and the card; `Coordinator.run()` returns a valid `Verdict`. |
| FastAPI server + SSE | **built, tested** | with `calc` configured a run returns the finished Verdict (`200`); without it, a preliminary result (`409` + `/report`). Stats include an estimated cost. |
| Web UI | **built, tested (46 tests)** | verdict card first, the case against second, ten live lanes, sections with status chips ("No findings" for empty ones). Checked in Chrome end to end. |
| Prompt-injection defence | **built, tested end to end** | `tests/e2e/test_e2e_decision.py`: an obedient model, two controls (no defences -> verdict flips to strong_buy; no sanitizer but consistency kept -> the run fails rather than ship it), and a planted-numbers case. |
| Cost/latency | **recorded** | tokens, seconds and an estimated `$` per agent and per run (`cost_usd_estimate`, run log). Prices are an ASSUMPTION (`agents/client.py::PRICES`). |
| Live Anthropic path | **written, never run** | no API key in this environment. |
| Test doubles | built | `tests/e2e/support/`: `fake_mcp` (real MCP), `fake_calc` (stand-ins for calc/ and audit/), `dev_app` (demo composition). |

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

**Last updated:** 2026-09-20 (Step 5, offline)
