# P3 status

Update whenever a capability moves from mock to real, or when blocked.
A PR that changes behaviour must update this file.

**Step:** 0 complete. **Next:** [roadmap](../roadmap.md) Step 1.
**Blockers:** none.

| Capability | State | Notes |
|---|---|---|
| `run_analysis` | mock | returns the ACME verdict fixture; signature unchanged from v1 |
| Coordinator | not started | Step 1 |
| MCP client (in-memory) | not started | Step 1 |
| MCP client (stdio) | not started | Step 3 |
| Financial Agent | mock | `fixtures/mock/analysis_financial.json` |
| Business Agent | mock | `fixtures/mock/analysis_business.json` |
| Valuation Agent | mock | `fixtures/mock/analysis_valuation.json` |
| Scenario Agent | mock | proposal lives in `fixtures/mock/scenarios.json` |
| Red Team | mock | `fixtures/mock/analysis_red_team.json` |
| Synthesizer | mock | verdict card and red-team response are in the fixture |
| Parallel execution | not started | Step 3 |
| Retry loop | not started | Step 5 |
| Report generator | not started | Step 2; templates drafted in `report/templates/` |
| FastAPI server | not started | Step 1 |
| SSE progress events | not started | Step 3 |
| `web/` UI | not started | Step 2; types and API client drafted |
| Prompt-injection test | not started | Step 5 |
| Cost/latency logging | not started | Step 5 |

## Prompts

All seven drafted and ready to tune: `shared_rules`, `financial`, `business`,
`valuation`, `scenario`, `red_team`, `synthesizer`, plus `verifier` (called by
P2).

**Last updated:** 2026-09-19 (Step 0 scaffold)
