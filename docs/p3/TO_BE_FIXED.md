# P3 — to be fixed, blocked, or not done yet

A living list of everything P3 has **not** finished or **cannot** finish yet, so we can come back to it.
[STATUS.md](STATUS.md) says what works; this file says what doesn't, and what would unblock it.

**How to use:** when you fix or unblock something, move its row to "Resolved" at the bottom with the date and commit.
When you find a new gap, add a row with an ID. Keep rows honest: "blocked" means we tried and hit a wall.

Legend: **Owner** is who must act. **Verify** is how we'll know it's fixed.

---

## A. Blocked on other partitions or on a team decision

| ID | What | Why it's blocked | Owner | Where it's written up | Verify when fixed |
|---|---|---|---|---|---|
| B1 | **Real mock MCP server** (`mcp_server.server.build_server`) | `mcp_server/` is still all `NotImplementedError`. P3 built and tested against its own test double (`tests/e2e/support/fake_mcp.py`). | P1 | [request](../requests/2026-09-19-p3-to-p1-mock-mcp-server.md) | Point the P3 MCP/coordinator tests at the real server object; they pass unchanged. |
| B2 | **Who injects the server / auditor in a real run** (import-boundary conflict) | Docs say P3 may not import `mcp_server/`/`audit/`, and also that mock mode is in-process. Both can't hold. P3 takes injected objects. Recommended: mock mode over **stdio**. | coordinator + P1 (needs an ADR if a 2nd import is allowed) | same request, "A boundary question" | A composition root exists and `orchestrator.api.run_analysis` runs the real pipeline in mock mode. |
| B3 | **A `Factsheet` for the auditor** | `audit.run_audit` needs one; no MCP tool returns it (`sp500_baseline` has no tool at all); P3 can't build it. | P1 / P2 | [report-inputs request](../requests/2026-09-19-p3-report-inputs.md) §2 | `Coordinator(auditor=real, factsheet=real)` runs `verify()` on a real state. |
| B4 | **Card prose fields have no home in `ResearchState`** | Contract lacks thesis / catalyst / risk / verdict word / $10k answer. P3 stores them as extras (`synthesis`, `market`, `company_name`). | all three (CONTRACT-CHANGE) | report-inputs request §1 | Either the convention is confirmed, or the fields are promoted into `schema/contracts/state.py`. |
| B5 | **Point-in-time rule for derived facts** (`filed_at = null`) | Real server needs a rule; P3's test double treats `null` as visible. | P1 | report-inputs request §3 | `resolve_fact` flags `is_future` correctly for derived facts. |
| B6 | **`calc/` and `audit/` are stubs** | `evaluate_scenarios`, `calculate_valuation`, `run_audit` return fixtures or raise in live mode. Needed for Steps 4-5. | P2 | roadmap Steps 2, 4 | Live-mode calls return real numbers. |
| B7 | **Live data** (`MODE=live`) | `data/` is skeleton. No EDGAR ingest, no market data. Needed for the Step 3 checkpoint ("one real ticker in live mode"). | P1 | roadmap Steps 1-4 | One real ticker produces a state with Financial + Business sections. |
| B8 | **No `ANTHROPIC_API_KEY` in the dev environment** | The live Anthropic path (`agents/client.py::complete`) has **never been run**. Expect small fixes on first use (structured-output schema, adaptive thinking, token accounting). | whoever has a key | STATUS.md | `LLM_MODE=live` run of the Financial Agent returns a valid `Analysis`; tokens recorded. |

## B. P3 work not done yet (roadmap)

| ID | What | Roadmap step | Notes |
|---|---|---|---|
| N1 | Valuation Agent (peers, methods, expectations reading) | Step 4 | Needs `calculate_valuation` (B6). |
| N2 | Scenario Agent, Red Team, Synthesizer | Step 5 | Prompts drafted by Step 0; agents are stubs. Red Team must get the RAW fact sheet (error J). |
| N3 | Retry loop (`orchestrator/retry.py`): targeted, max 2, then mark `unverified` | Step 5 | `verify()` today is a single pass; failed claims stay `failed` and render as UNVERIFIED. |
| N4 | LLM `verify_claim` callable for the auditor (verifier prompt, cheaper model) | Step 5 | `prompts/verifier.md` exists; nobody has written the callable P2 will be handed. |
| N5 | Full fifteen-section report, S&P comparison section | Step 5 | Needs N1-N2 and calc. |
| N6 | `orchestrator.api.run_analysis` wired to the Coordinator | after B1/B2/N2 | Still returns the ACME verdict fixture in mock mode. |
| N7 | Full prompt-injection e2e ("verdict must not move") with a control run | Step 5 | Guard is built and unit/e2e tested at the agent + coordinator level. The obedient-model test from the v1 branch (`p3-v1-backup`, `tests/e2e/test_e2e_injection.py`) needs the Synthesizer to port. |
| N8 | Measured per-run cost/latency in live mode | Step 5 | Tokens and seconds are recorded; `$` uses assumed prices (`agents/client.py::PRICES`, copied from the claude-api skill 2026-06-24). |
| N9 | Agents call MCP tools themselves (tool-use loop) | later (Step 3 did not need it) | Today the coordinator pre-fetches sections and facts and passes them in. `Agent.tools` already declares each agent's allowed set. |
| N10 | Tune prompts against ACME, then one real filing | Steps 1/3 | `financial.md` and `business.md` still say `TODO(...): tune`. |
| N11 | Generate `web/lib/types.ts` from `schema/*.json` | Step 3 | Hand-maintained; a test checks it against the fixture. |
| N13 | **Step 3 live checkpoint**: one real ticker in live mode, Financial + Business sections, schema-valid | Step 3 | Blocked by B1, B7, B8. `StdioMcpClient` is built and tested against the test double; it targets `python -m mcp_server.server` by default. |
| N14 | Tune `business.md` against a real filing (wording-change comparison needs the PRIOR filing's text, which the coordinator does not fetch yet) | Step 3 | Today each agent sees only the latest section of each item. |
| N12 | Backtest `redact` hook supplied by P2 | Step 6 | P3's side (applied centrally before any model call) is done and tested. |

## C. Known small issues

| ID | What | Fix |
|---|---|---|
| S1 | The disclaimer shows twice on a report page (the report's own + site footer). Deliberate (the report's must travel with the Verdict). | Dedupe in CSS if it reads as noise. |
| S2 | `agents/requirements.txt` lists `sse-starlette` (Step 0) but SSE is plain `StreamingResponse`. | Drop the dependency or use it. |
| S3 | `web` has no `lint` script (Step 0's `next lint` had no ESLint config). | Add an ESLint flat config, or leave typecheck as the gate. |
| S4 | The MCP SDK logs every request at INFO, which is noisy in test output. | Set the `mcp` logger level in test config. |
| S5 | Fixture: `claim:financial:revenue` says "five billion dollars" but its value is `0.4`; `facts.json` lacks `gross_profit`, `receivables`, `sbc` (FY2025) that the mock analysis cites; the mock `ResearchState` has no synthesizer output. | Coordinator: fix in `scripts/gen_mock_fixtures.py`, regenerate, run contract tests. |
| S6 | Default model is `claude-sonnet-5` (Step 0 decision); the claude-api skill's default is `claude-opus-5`. Not measured. | Revisit at Step 5 with real cost and quality numbers. |
| S7 | v1 P3 work is preserved only on branch `p3-v1-backup`. | Delete the branch once N7 is ported. |
| S9 | The demo composition (`tests/e2e/support/dev_app.py`) serves the MCP **test double**; swap in the real server when B1 lands. | Change one line in `dev_app.py`. |
| S10 | Mock-path only: mock analysis fixtures carry `numbers` by `derived_from` path, and only the paths whose facts exist in `facts.json` become `fact_ids`. The UI can therefore show "40.0%" beside `fact:ACME:revenue:FY2025` (really gross margin). The live path builds numbers from the cited fact rows, so it cannot do this, and the P2 verifier's `prose_number_mismatch` should catch it. | Fix with S5 (add the missing facts to the fixture). |
| S11 | The HTTP API grew beyond `docs/pipeline.md`'s three endpoints: `GET /api/runs/{id}/report`, `/stats`, `/api/config`, and a `409 {"status":"preliminary"}` on `GET /api/runs/{id}`. | Coordinator: document in `docs/pipeline.md`. |
| S12 | Origins allowed by CORS are hard-coded to `localhost:3000` / `127.0.0.1:3000`; a Next server on another port shows the browser's opaque "Failed to fetch" (the UI now explains that the server is unreachable). | Make it an env var if the demo needs another origin. |
| S8 | `plan.txt` was archived by the restructure; the team's context now lives in `ARCHITECTURE.md`, `docs/` and `CLAUDE.md`. | Nothing; noted so nobody looks for it. |

---

## Resolved

- **2026-09-19, Step 3 (offline parts):** Business Agent (each agent is shown only its own filing items); the financial/business pair run **concurrently** with a deterministic canonical-order merge (a barrier test fails if they run sequentially); per-agent progress events wired through the server via a composition hook (`server.configure`); preliminary-result path (`409` + `/report`) and UI support; a demo composition (`tests/e2e/support/dev_app.py`); friendlier unreachable-server message. Checked in a real browser: both lanes `running` at once, then the preliminary report.

**Last updated:** 2026-09-19
