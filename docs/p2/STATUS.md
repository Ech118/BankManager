# P2 status

Owner updates this file whenever a capability moves from mock to real, or when blocked.

| Capability | State (mock / real / blocked) | Notes |
|------------|-------------------------------|-------|
| calc.compute_metrics | real | Pure function of any schema-valid factsheet (not ACME-specific). Hand-checked against ACME (`calc/tests/test_metrics.py`) and against Apple's FY2023 10-K public figures. |
| calc.reverse_dcf | real | Bisection solver + sensitivity grid (`calc/dcf.py`), config in `calc/config.py`. |
| calc.evaluate_scenarios | real | Validates probabilities sum to 1; base-rate prior + hard-capped prior_shift (`calc/scenarios.py`). Cap proven by `calc/tests/test_scenarios.py`. |
| calc.derive_scores | real | Fixed rubric, documented in `docs/p2/rubric.md`. |
| calc.validate_consistency | real | `calc/consistency.py`. |
| audit.run_audit | real | Numbers-trace, evidence-quote, disclaimer, consistency checks (`audit/checks.py`). Catches an injected fake number and a fabricated quote (`audit/tests/test_run_audit.py`). |
| backtest anonymizer | real | Regex-level redaction of company name/ticker/dates -> relative period tokens (`backtest/anonymize.py`). Known limitation: does not catch arbitrary product names (documented in `backtest/README.md`). |
| backtest harness/grader/calibration | real (against mocks) | `backtest/harness.py` calls `data.api` + `orchestrator.api` for real; grading/calibration in `backtest/grade.py` / `backtest/calibration.py`. Runs end to end against the ACME mock fixtures. `point_in_time_verified` is `False` today because P3's orchestrator stub does not yet honour `as_of`/`redact` - this is P3's Step-0 stub catching up, not a P2 gap; harness will start reporting `True` once P3 wires the real pipeline. |
| predictions log | real | Append-only `<date>_<ticker>_<inputhash>.json` writer + grader (`predictions/logger.py`). |

Tests: `python3 -m pytest tests/contracts calc/tests audit/tests backtest/tests predictions/tests -q` (142 passed, 1 skipped live test, at last run). `make check-contracts` and `scripts/check_ownership.sh p2` both pass.

Blocked on: nothing. Backtest's `point_in_time_verified` flag will flip to `True` once P3 replaces the `orchestrator.api.run_analysis` stub to honour `as_of`/`redact`, and once P1's real (non-mock) point-in-time XBRL lands - no action needed from P2 for that.

Last updated: 2026-09-19.
