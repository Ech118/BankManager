# P2 status

Update whenever a capability moves from mock to real, or when blocked.
A PR that changes behaviour must update this file.

**Step:** metrics, valuation, scenarios and scores complete. **Next:** `audit/`.
**Branch:** `p2-port`, based on P1's `p1-step2` (P1's PRs are not merged yet), so
`scripts/check_ownership.sh p2` must be run as `BASE=HEAD scripts/check_ownership.sh p2`
with the P2 paths staged. Against `origin/main` it reports P1's files.
**Blockers:** none. Three things wanted from P1, none blocking: see
`docs/requests/2026-09-19-p1-to-p2-split-warning-and-missing-metrics-response.md`.

| Capability | State | Notes |
|---|---|---|
| `compute_metrics` | **real** | every pinned ACME number reproduced exactly; runs on all five real recordings |
| derived facts + lineage | **real** | one `FinancialFact` per computed number in `metrics["derived_facts"]`, `filed_at` = latest input |
| `metrics["input_facts"]` | **real** | market/consensus facts calc/ had to mint an id for, so the verifier can resolve them |
| split-basis rule | **real** | per-share growth across a share-count break is `unavailable` with the reason; totals unaffected |
| partial scope (banks) | **real** | FCF, gross margin and EV multiples `not_applicable`; P/B, BVPS and ROE computed |
| quality flags | **real** | DSO, inventory days, buyback-flattered EPS, FCF conversion, SBC |
| `reverse_dcf` | **real** | ported bisection solver plus the 9-cell sensitivity grid |
| `calculate_valuation` | **real** | multiples, peers, forward and reverse DCF; a skipped method records why. P1's wrapper must pass `request["factsheet"]` (request filed) |
| forward DCF | **real** | 3-year average FCF base; growth = trailing REVENUE CAGR bounded to [3%, 15%], fading linearly to terminal growth over 10 years; every bound recorded |
| TTM multiples | **ready** | P/E, P/S, P/FCF and EV/EBITDA use `<metric>_ttm` facts when the factsheet carries them, else the latest full year; `valuation.basis.by_multiple` labels each |
| peer P/E and P/S medians | **ready** | computed from peer `revenue` / `net_income` when P1 sends them; today's recordings carry market cap only |
| historical multiples | **unavailable** | reason `"no price history source"`; the functions are complete and take a series |
| peer multiples | **degraded** | real recordings carry peer market caps only, so the peer median is `unavailable` with a reason |
| `evaluate_scenarios` | **real** | reproduces the pinned ACME result (-1.945%/yr against 7%); derives `eps_at_horizon`, per-horizon values, and the bear-weight flip point |
| weight clamping | **real** | matches the worked example in `docs/pipeline.md` and `fixtures/mock/scenario_weights_clamped.json`; every clamp recorded |
| prior cap | **real** | shifts summed before the cap; an unreasoned shift is dropped, not capped |
| `derive_scores` | **real** | rubric published in [rubric.md](rubric.md); reproduces the pinned 3/3/4 |
| `validate_consistency` | **real** | six checks, including both of P3's own rules |
| `run_audit` | mock | returns the ACME audit fixture |
| deterministic checks | not started | seven of them |
| LLM claim check | not started | prompt drafted in `prompts/verifier.md` |
| retry routing | not started | table in `docs/verification.md` |
| `backtest/` | not started | |
| `predictions/` | not started | |
| `docs/p2/rubric.md` | **written** | bands, horizon divisors, the penalty, and a constants changelog |

## Known gaps in Step 1

- **`restated_prior_period`** is the one ACME quality flag calc/ cannot
  reproduce: a restatement is visible only on the superseded `FinancialFact`, and
  the `Factsheet` carries neither the superseded facts nor a gap naming one.
  Requested from P1.
- **Peer multiples** are unavailable on every real recording (peers carry a
  market cap and nothing else), so `valuation.vs_peers` is unavailable with the
  reason attached rather than wrong.
- **`config.DSO_INCREASE_FLAG` was lowered from 0.10 to 0.05** when the flag was
  implemented, so the ACME `dso_rising` flag in `fixtures/mock/metrics.json`
  fires. Severity now comes from one threshold per flag plus a shared
  `FLAG_SEVERITY_STEPS` ladder.

## Additive keys calc/ puts on `Metrics` (outside the contract's required fields)

`Metrics` tolerates extras, and P3 tolerates unknown keys, so these need no
contract change: `derived_facts`, `input_facts`, `cagr`, `returns.roe`,
`per_share.book_value_per_share`, `valuation.p_b`,
`valuation.primary_multiple`, `growth.<period>.net_income_yoy`, `scope_level`,
`notes`. Every unavailable ValueObject also carries `unavailable_reason`, and a
metric that does not describe the filer at all carries `not_applicable: true`.

## Known gaps in Step 2

- **Multiples divide the latest FULL YEAR** while a data provider quotes TTM,
  because no recording carries a TTM fact yet. The switch is implemented: with a
  TTM EPS of $9.38 on AAPL's factsheet P/E reads 35.8x instead of 45.1x, matching
  what a finance site shows. `valuation.basis` names the basis per multiple.
- **Peer medians are unavailable** on every real recording (0 of 6 peers carry a
  multiple). `peer_table` computes P/E, P/S, P/FCF, P/B and EV/EBITDA from raw peer
  fields the moment P1 sends any; tested against a synthetic peer set.
- **The 3-year FCF average cuts both ways.** It fixes KO (FY2025 sits 19.7% below
  the average) and distorts NVDA, whose FCF went 27bn -> 61bn -> 97bn, so the
  average is 37% below the current run-rate. `fcf_base.margin_based_alternative`
  publishes the other option - the average FCF MARGIN applied to the latest year's
  revenue - which agrees with the dollar average for KO (6.78bn against 6.59bn) and
  keeps NVDA's scale (97.7bn against 61.5bn). Switching the default is a judgement
  call, so both numbers ship.
- **Historical multiples are unavailable by design**: no price history source.

## Known gaps in Step 3

- **`eps_at_horizon` is derived by calc/**, answering P3's blocking question
  (`docs/requests/2026-09-20-p3-to-p2-step5-calc-contract-response.md`). An
  agent-supplied value is recomputed and the disagreement recorded.
- **The per-horizon annualized return is horizon-invariant by construction**: one
  scenario CAGR implies one annual rate. `by_horizon.cumulative_return` is the
  figure that differs across 0-12m / 1-3y / 3-5y.
- **`sp500_expected_return` is `config.SP500_EXPECTED_RETURN`** (0.07): no
  factsheet publishes an expected index return. The factsheet's forward P/E,
  earnings yield and risk-free rate are echoed beside it, and calc/ prefers
  `sp500_baseline.expected_return` the day P1 publishes one.

## The discount rate

`DISCOUNT_RATE` 0.09 and `TERMINAL_GROWTH` 0.03, both NOMINAL: the cash flows are
as-filed dollars and nothing adjusts for inflation. The reverse DCF implying
17-23% growth for every company is **not** caused by the rate - a zero-growth
perpetuity is worth 17.2x FCF at 9%/3%, and these companies trade at 48-87x their
smoothed FCF base. A full point off the discount rate moves AAPL's implied growth
by 2.7 points. Full table, and the recommendation to derive the rate from the
factsheet's risk-free rate plus a configured ERP (4.25% + 4.5% = 8.75%), in
[rubric.md](rubric.md).

**Last updated:** 2026-09-20 (DCF: smoothed base, fading revenue-CAGR growth, TTM multiples, peer medians)
