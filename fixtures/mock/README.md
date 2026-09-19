# fixtures/mock  (FROZEN, coordinator only)

Sample data for the **fictional company ACME**. NOT real market data.
Regenerate with `make gen-mock` (`scripts/gen_mock_fixtures.py`); do not hand-edit the JSON.
Every file validates against `schema/` (`make check-contracts`).

| File | Schema | Produced in real life by |
|------|--------|--------------------------|
| factsheet.json | factsheet | P1 `data.api.build_factsheet` |
| metrics.json | metrics | P2 `calc.api.compute_metrics` |
| analysis_*.json | analysis | P3 agents (forensic, business, valuation, red_team) |
| scenarios.json | scenarios | P3 Valuation agent |
| scenario_result.json | scenario_result | P2 `calc.api.evaluate_scenarios` |
| audit.json | audit | P2 `audit.api.run_audit` |
| verdict.json | verdict | P3 `orchestrator.api.run_analysis` |
| sections/*.txt | (text) | P1 `data.api.get_section_text` |

Mock-only tickers: `ACME` (in scope), `BANKX` (out of scope: exercises the rejection path).
Story of the data: ACME is a good business at 33.8x earnings; base case trails the S&P; verdict AVOID.
