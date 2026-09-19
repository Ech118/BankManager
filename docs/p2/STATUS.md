# P2 status

Update whenever a capability moves from mock to real, or when blocked.
A PR that changes behaviour must update this file.

**Step:** 0 complete. **Next:** [roadmap](../roadmap.md) Step 2.
**Blockers:** none.

| Capability | State | Notes |
|---|---|---|
| `compute_metrics` | mock | returns the ACME fixture; `as_of` dropped per amendment 2 |
| `reverse_dcf` | mock | fixture already carries a 9-cell sensitivity grid |
| `calculate_valuation` | mock | the MCP-exposed entry point |
| `evaluate_scenarios` | partial | **really** rejects weights not summing to 1; rest is fixture |
| weight clamping | not started | algorithm specified in `docs/pipeline.md`; demonstrated by `fixtures/mock/scenario_weights_clamped.json` |
| prior cap | mock | fixture respects it; `test_prior_shift_respects_cap` passes |
| `derive_scores` | mock | rubric table drafted in `calc/config.py` |
| `validate_consistency` | mock | returns ok; thresholds drafted in `scenarios/consistency.py` |
| `run_audit` | mock | returns the ACME audit fixture |
| deterministic checks | not started | Step 2; seven of them |
| LLM claim check | not started | Step 5; prompt drafted in `prompts/verifier.md` |
| retry routing | not started | Step 2; table in `docs/verification.md` |
| `backtest/` | not started | Step 6 |
| `predictions/` | not started | Step 6 |
| `docs/p2/rubric.md` | not written | must exist before `derive_scores` goes real |

**Last updated:** 2026-09-19 (Step 0 scaffold)
