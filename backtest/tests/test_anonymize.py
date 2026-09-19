"""Unit tests for backtest.anonymize (plan.txt error A)."""
from backtest.anonymize import build_redactor


def test_strips_company_name_and_ticker():
    redact = build_redactor("Acme Corporation (fictional mock)", "ACME", "2025-06-01")
    text = "Acme Corporation (fictional mock) said ACME shares rose."
    out = redact(text)
    assert "Acme" not in out
    assert "ACME" not in out
    assert "[COMPANY]" in out
    assert "[TICKER]" in out


def test_iso_dates_become_relative_to_as_of():
    redact = build_redactor("Acme Corporation", "ACME", "2025-06-01")
    out = redact("The filing covers the period ended 2025-06-01, following 2024-12-31.")
    assert "2025-06-01" not in out
    assert "2024-12-31" not in out
    assert "[T]" in out       # same year as as_of
    assert "[T-1y]" in out    # one year before as_of


def test_bare_years_become_relative():
    redact = build_redactor("Acme Corporation", "ACME", "2025-06-01")
    out = redact("Revenue grew in 2024 and again in 2025.")
    assert "2024" not in out
    assert "2025" not in out
    assert "[T-1y]" in out
    assert "[T]" in out


def test_month_name_dates_become_relative():
    redact = build_redactor("Acme Corporation", "ACME", "2025-06-01")
    out = redact("Filed on June 1, 2025 covering fiscal 2024.")
    assert "2025" not in out


def test_empty_text_is_returned_unchanged():
    redact = build_redactor("Acme Corporation", "ACME", "2025-06-01")
    assert redact("") == ""
    assert redact(None) is None
