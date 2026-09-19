"""Unit tests for backtest.harness (plan.txt 15.14 P2 step 7 "Done when:
... backtest runs on ACME-style anonymized fixtures end to end")."""
from backtest.harness import run_backtest, run_case


def test_run_case_end_to_end_on_acme_mock_fixture():
    result = run_case("ACME", "2025-06-01", realized_annualized_return=0.20)
    assert "error" not in result
    assert result["ticker"] == "ACME"
    assert result["beat_sp500"] is True
    assert "point_in_time_verified" in result


def test_run_case_flags_when_orchestrator_stub_ignores_as_of():
    """P3's Step 0 stub does not yet honour as_of/redact (plan.txt Phase 1: a
    partition falling behind must not block the others) - the harness must
    surface that instead of silently claiming a verified point-in-time run."""
    result = run_case("ACME", "2025-06-01", realized_annualized_return=0.20)
    assert result["point_in_time_verified"] is False
    assert "warning" in result


def test_run_case_reports_out_of_scope_ticker_without_crashing():
    result = run_case("BANKX", "2025-06-01", realized_annualized_return=0.20)
    assert "error" in result
    assert "build_factsheet" in result["error"]


def test_run_case_reports_as_of_before_any_filing_without_crashing():
    result = run_case("ACME", "2020-01-01", realized_annualized_return=0.20)
    assert "error" in result


def test_run_backtest_runs_multiple_cases():
    cases = [
        {"ticker": "ACME", "as_of": "2025-06-01", "realized_annualized_return": 0.20},
        {"ticker": "ACME", "as_of": "2024-06-01", "realized_annualized_return": -0.05},
        {"ticker": "BANKX", "as_of": "2025-06-01", "realized_annualized_return": 0.10},
    ]
    results = run_backtest(cases)
    assert len(results) == 3
    assert "error" in results[2]  # BANKX is out of scope
