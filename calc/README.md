# calc

**Owner: P2 (Calc, Audit & Eval).** Only the owner edits this directory (plan.txt 15.4).

All deterministic math: metrics, reverse DCF, scenario evaluation, base-rate prior with capped shift, score rubric, consistency checks. No I/O, no LLM. Public interface: api.py. Build order: plan.txt 15.14 P2.

## Layout
- `value.py` - value-object helpers (never guess, never 0 for missing data).
- `config.py` - assumption constants (discount rate, terminal growth, base-rate prior, prior-shift cap, score bands).
- `metrics.py` - `compute_metrics`: margins, growth, cash flow, balance sheet, per-share, quality flags, valuation.
- `dcf.py` - `reverse_dcf`: bisection solver + sensitivity grid.
- `scenarios.py` - `evaluate_scenarios` + `derive_scores`: probability validation, price targets/returns, capped prior shift, score rubric (see `docs/p2/rubric.md`).
- `consistency.py` - `validate_consistency`.
- `api.py` - the frozen public interface; thin wrappers over the modules above.
- `tests/` - unit tests hand-checked against the ACME mock fixture and against Apple's FY2023 10-K public figures.
