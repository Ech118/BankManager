# P3 -> P1 / P2 / coordinator: three gaps found while building Roadmap Step 2

**From:** P3  **Urgency:** (1) and (2) block wiring the real verifier and real report end to end.

## 1. The card's prose fields have no home in `ResearchState` (needs a decision)

`VerdictCard` needs `thesis`, `primary_catalyst`, `biggest_risk`, `valuation`, `business_quality`,
`financial_strength`, `verdict`, `ten_thousand_dollar_answer` and the red-team exchange; it also needs `price`,
`market_cap` and the company name. The mock `research_state.json` holds none of these (its `decision` section
has one prose claim, and `agent_outputs` has no synthesizer entry), and ADR 0004 says the report must be a pure
function of the state.

**What P3 did (additive, no contract change):** the Coordinator stores three extra fields in the state's
`extra="allow"` space: `company_name`, `market` (a `MarketSnapshot`) and `synthesis` (`agents/synthesis.py`).
`orchestrator/report/generator.py` reads them and raises `ReportInputError` if any is missing; it never invents a
value. The Synthesizer's numbers are never involved: scores, probability and returns come from
`state.scenario_result` only.

**Ask:** confirm this convention, or promote `synthesis` / `market` / `company_name` into
`schema/contracts/state.py` through a CONTRACT-CHANGE PR (P3 will apply it as coordinator once all three approve).

## 2. Nothing on the MCP surface yields a `Factsheet`, but `audit.run_audit` requires one

`audit.api.run_audit(state, factsheet, get_text, verify_claim)` takes a `Factsheet`. P3 may not import `data/`, and
none of the ten MCP tools returns a Factsheet (its `sp500_baseline` has no tool at all). So P3 cannot build one.

**What P3 did:** `Coordinator(auditor=..., factsheet=...)` takes both as **injected** callables. `verify()` runs the
auditor once, stores `state.verification`, and marks every claim `verified` / `failed`. Tested with a stub auditor.

**Ask (P1/P2):** either add a `get_factsheet` MCP tool, or change what `run_audit` needs (for example, resolve
facts through an injected callable like `get_text`). Until then the real composition root has to hand P3 a factsheet.

## 3. Derived facts have no `filed_at`

`fact:ACME:fcf:FY2025` (`source_kind: derived`) has `filed_at = null`. P3's test double crashed comparing it to
`as_of`. The real server's point-in-time filter needs a rule for these (P3's double treats `null` as visible on the
assumption that its inputs were already filtered). `resolve_fact` should also flag `is_future` from the facts a
derived value was computed from.

## Fixture notes (coordinator)

- `claim:financial:revenue` says "Revenue reached five billion dollars" but its `value` is `0.4` (a fraction, and
  really the gross margin). The report renders "(40.0% - fact)" next to that sentence, which is exactly what the
  `prose_number_mismatch` check should catch. Worth fixing in the generator script.
- `fixtures/mock/analysis_financial.json` cites facts missing from `facts.json` (`gross_profit`, `receivables`,
  `sbc`, FY2025); the agent ignores unknown fact ids and logs it.
