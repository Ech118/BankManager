# Contract changelog

Every change to `schema/` is recorded here. Breaking changes need written
approval from all three partitions
([CONTRIBUTING.md](../CONTRIBUTING.md#contract-change-process)).

---

## 2.1.0 — 2026-09-20 — `get_factsheet` MCP tool

**ADDITIVE.** No existing shape changed; old readers keep working.

Proposed in `docs/requests/2026-09-20-p1-to-all-get-factsheet-tool.md`.

### Added

- **`GetFactsheetRequest` / `GetFactsheetResponse`** in
  `schema/contracts/tools.py`, registered as `get_factsheet`. The tool count
  goes from ten to eleven; ten data tools now wrap `data/`.

  `GetFactsheetRequest` inherits `DataToolRequest`, so it carries a required
  `as_of` like every other data tool. `GetFactsheetResponse.factsheet` is
  `Factsheet | None`; `None` means the ticker is in scope but has no reportable
  history, while an out-of-scope ticker raises.

  It exists because `audit.run_audit(state, factsheet, ...)` requires a
  `Factsheet` and the orchestrator may not import `data/` (ADR 0007), so there
  was no contract-described path from the partition that produces a factsheet to
  the one that consumes it. P3 was bridging it by injection.

### Changed

- `tests/contracts/test_models.py` — the tool-count assertion is 11.

### Unchanged

Every other model. `Factsheet` is imported into `tools.py`, not edited.
`STATE_VERSION` did not move: the state shape is untouched. No `api.py`
signature changed — `data.api.build_factsheet(ticker, as_of)` already existed
and is what the tool wraps.

### Mock fixtures

`make gen-mock` was run. The only lines that changed are `schema_version`.

---

## 2.0.0 — 2026-09-19 — Truth-layer restructure

**BREAKING.** Approved by all three partitions as part of the Step 0
restructure.

### The change in one line

The pydantic models in `schema/contracts/` are now the **source of truth**, and
`schema/*.json` is **generated** from them by `make gen-schema`.

`tests/contracts/test_schema_export.py` fails the build if the committed JSON
drifts from the models, so the two cannot disagree silently.

### Added

- **`schema/contracts/`** — the pydantic contract package. Includes
  `interfaces.py`, holding the `FactRepository`, `FilingRepository`,
  `MarketRepository` and `McpClient` Protocols.
- **`FinancialFact`** (`financial_fact.json`) — the truth-layer row type, with
  `fact_id`, provenance, `derivation` and `superseded_by`.
- **`Claim`** (`claim.json`) — the unit an agent may assert. Numbers must cite
  `fact_id`s.
- **`ResearchState`** (`research_state.json`) — the object the report is
  rendered from, with fourteen owned sections and `STATE_VERSION`.
- **`Filing` / `FilingSection`** (`filing.json`) — structural parsing with
  character offsets.
- **`MarketSnapshot` / `CompanyProfile`** — all market fields at one instant.
- **`tools.json`** — request/response shapes for the ten MCP tools.
- **`ScenarioWeights` / `WeightClamp`** — the audit record for scenario weight
  bounding.
- `expected_return_vs_sp500` on `ScenarioResult` and on the verdict card.
- `probability_rationale` on `Scenario`; `shift_reasons` and `source` on the
  prior.
- Verification detail: `issue_type`, `claim_id`, `expected`/`actual`,
  `RetryDirective`, claim counters.

### Changed (breaking)

- **Horizon keys** `1y` / `3y` / `5y` → `short_term` / `medium_term` /
  `long_term`, labelled 0-12m / 1-3y / 3-5y. They now match `Scores`, so returns
  and scores line up.
- **`Factsheet.market`** is now a full `MarketSnapshot` (adds `as_of`,
  `retrieved_at`, `source_id`, `total_debt`, `cash`, `currency`).
- **`Factsheet.filing_sections`** entries are `FilingSection` objects, with both
  a `section_id` and a `source_id`.
- **`audit.json`** is now a `VerificationResult`: issues carry an `issue_type`
  and the report carries claim counters.
- **Agent roster**: `forensic` → `financial`; added `scenario` and `verifier`;
  removed `scout`, `management` and `balance_sheet` (merged into `financial` and
  `business`). `analysis_forensic.json` → `analysis_financial.json`.
- **`data/api.py`** gained the MCP-aligned reads (`search_filings`,
  `get_filing_section`, `search_filing`, `get_financial_facts`,
  `get_market_snapshot`, `get_company_profile`, `get_peer_companies`,
  `search_news`, `resolve_fact`). `get_xbrl` and `list_sections` are superseded.
- **`calc/api.py`** gained `calculate_valuation` and `prior_shifts`.
- **`audit/api.py`**: `run_audit(state, factsheet, get_text, verify_claim=None)`
  — it now reads a `ResearchState`.
- **`compute_metrics` dropped its `as_of`.** No function receiving a factsheet
  also takes a date; the factsheet's `as_of` is authoritative, and
  `test_signatures.py` enforces it.
- **`MODE` / `LLM_MODE`** replace `BM_MODE` / `BM_LLM`. The old names are still
  read, so existing shells keep working.

### Unchanged

`orchestrator.api.run_analysis(ticker, as_of=None, redact=None)`, every ACME
number, the `ValueObject` shape and its four conditional rules, the fractions/
full-USD/ISO-date conventions, and the prior cap with
`test_prior_shift_respects_cap`.

### Note on the generated JSON

pydantic cannot infer `if`/`then` from a validator, so `ValueObject` overrides
`__get_pydantic_json_schema__` to re-attach its four conditional rules. The
generated schema is therefore **stronger** than v1.0.0's: the rules now appear
inline in every consumer's `$defs`, not only in `common.json`.

---

## 1.0.0 — 2026-09-19 — Step 0 skeleton

Initial hand-written JSON Schemas: `common`, `factsheet`, `metrics`, `analysis`,
`scenarios`, `scenario_result`, `audit`, `verdict`. ACME mock fixtures, `api.py`
stubs, contract tests.

Superseded by 2.0.0. Recoverable from git history at tag `step0`.
