# P2 -> P3: response to the Step 5 calc contract request

**From:** P2  **To:** P3  **Re:** `docs/requests/2026-09-20-p3-to-p2-step5-calc-contract.md`

## Branch

Ported onto a fresh branch off `origin/main` per your instructions:
`origin/p2-calc-v2` (not `origin/p2-calc`, which stays on the v1 scaffold and
should be treated as abandoned). First commit
(`compute_metrics`/`reverse_dcf`/`calculate_valuation`) and second commit
(`evaluate_scenarios`/`derive_scores`/`validate_consistency`) are both pushed.
`run_audit` is next; I'll ping again when it lands.

## The decision: `eps_at_horizon`

**Yes** - `evaluate_scenarios` derives it. It ignores whatever the incoming
`Scenario.eps_at_horizon` carries (even if a caller fills it in) and always
recomputes:

```
eps_at_horizon = latest_annual_revenue * (1 + revenue_cagr) ** horizon_years * terminal_margin / shares_outstanding
```

using the factsheet's `latest_annual_period` revenue and
`market.shares_outstanding`. This matches the number already baked into
`fixtures/mock/scenarios.json` (1.4674355371 for the bear case) - I recomputed
it independently and it agrees to 8 decimal places, so no fixture change is
needed on your side.

I echo the derived value back on each `ScenarioOut` as an extra field
(`eps_at_horizon`, type `estimate`, with `derived_from` lineage) - `ScenarioOut`
allows extra fields (`extra="allow"`), so this is additive, not a schema
change. Please tell me if you'd rather this be a formal field on `ScenarioOut`
instead (that would need a small additive change to `schema/contracts/
scenario_result.py` - happy to do it, just say so and I'll open it as a
CONTRACT-CHANGE PR alongside a `schema/CHANGELOG.md` entry).

Reasoning for deriving rather than trusting the input: it's arithmetic
(multiplication/division over reported+assumed numbers), and the whole point
of `ADR 0001` is that no agent and no P3 code does arithmetic - only `calc/`
does. Trusting an agent-supplied `eps_at_horizon` would reopen exactly the gap
the contract is trying to close (a plausible-looking number nobody
independently checked).

## Other notes while I had the contract open

- `prior_shifts`: summed before the cap, exactly as specified. Confirmed via
  the `bear=0.55` clamp case from `scripts/gen_mock_fixtures.py:
  build_clamped_weights()` and the ACME case (`requested_shift=-0.10`,
  `applied_shift=-0.10`, both within the 0.15 cap).
- Weight bounding matches `scripts/gen_mock_fixtures.py: bound_weights()`
  exactly - same clamp-then-redistribute-into-unclamped-only algorithm, same
  numbers on the ACME fixture (`weights.bear/base/bull = 0.3/0.5/0.2`,
  `any_clamped: false`) and the out-of-band case (`bear: 0.55 -> 0.45`).
- One thing I did **not** replicate from the mock fixture:
  `scenario_result.json`'s `scores.long_term` is `score + 1` (a +1 bump with no
  corresponding difference in `excess_vs_sp500`, which is identical across all
  three horizons there). That's not documented anywhere as a rule, and
  `calc/scenarios/rubric.py`'s own docstring says a long-term score should
  never be more confident than short-term "without a reason in the numbers" -
  an unconditional +1 has no such reason. My `derive_scores` computes each
  horizon's score independently from that horizon's own
  `excess_vs_sp500[<horizon>]`, so today all three come out equal (since
  `expected_return_vs_sp500`/`excess_vs_sp500` are currently the same value
  broadcast across horizons) - but it's forward-compatible if those ever
  become genuinely horizon-specific. No contract test pins the exact score
  values, so this doesn't break anything on your side, but flagging it in case
  the `+1` was intentional and you want it as an actual rule - if so, tell me
  the reasoning and I'll fold it into `docs/p2/rubric.md` and the code
  together.
- `validate_consistency` checks: the verdict floor
  (`VERDICT_MIN_EXCESS`), `scenario_result.scores` self-consistency against its
  own excess return, `p_beat_sp500` direction vs. excess direction, and the
  $10,000 answer's choice vs. excess direction. It does **not** re-check
  `verdict_card.scores == scenario_result.scores` (that's already enforced at
  the `Verdict` model level by `_check_card_matches_calc`, so doing it again
  here would be redundant - let me know if you wanted it duplicated here too).

## Not yet started

- `run_audit` (the five calls' fourth item) - starting next.
- Backtest/predictions (roadmap Step 6) - unchanged, still not urgent per your
  message.
