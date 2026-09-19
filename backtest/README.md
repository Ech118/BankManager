# backtest

**Owner: P2 (Calc, Audit & Eval).** Only the owner edits this directory (plan.txt 15.4).

Anonymized point-in-time backtest and calibration chart (label 'illustrative' unless N >= 100).

## Layout
- `anonymize.py` - `build_redactor(company_name, ticker, as_of)`: strips company name/ticker/dates, dates become tokens relative to `as_of` (e.g. `[T-1y]`). Known limitation: regex-level, not NER - it does not catch arbitrary product names a filing might mention; only company name, ticker, and dates/years are guaranteed anonymized.
- `grade.py` - `grade_case`: compares a verdict's 5y prediction to a realized return supplied by the caller (P2 does not fetch market data itself).
- `calibration.py` - `compute_calibration` + `render_calibration_svg`: buckets by predicted P(beat S&P), labelled "illustrative" below N=100 (error B), dependency-free SVG output.
- `harness.py` - `run_case`/`run_backtest`: calls `data.api.build_factsheet` (to build the redactor) and `orchestrator.api.run_analysis` (with `as_of`/`redact`), only through their `api.py` (plan.txt 15.8). Sets `point_in_time_verified: False` with a `warning` when the orchestrator's response wasn't actually produced in point-in-time mode, instead of silently presenting an unverified result as clean.
