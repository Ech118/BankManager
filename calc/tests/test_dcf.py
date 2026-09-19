"""Unit tests for calc.dcf (plan.txt 15.14 P2 step 2: "ALWAYS return a
sensitivity grid" / error D)."""
import pytest

from calc import config
from calc.dcf import _pv_at_growth, compute_reverse_dcf, solve_implied_growth


def test_solved_growth_round_trips_through_the_pv_formula():
    ev, fcf0, r, tg, n = 19_900_000_000, 600_000_000, 0.09, 0.03, 10
    g = solve_implied_growth(ev, fcf0, r, tg, n)
    assert _pv_at_growth(g, r, tg, fcf0, n) == pytest.approx(ev, rel=1e-6)


def test_reverse_dcf_always_returns_a_sensitivity_grid():
    out = compute_reverse_dcf(19_900_000_000, 600_000_000)
    grid = out["sensitivity_grid"]
    assert len(grid) == len(config.DCF_SENSITIVITY_DISCOUNT_RATES) * len(config.DCF_SENSITIVITY_TERMINAL_GROWTHS)
    for row in grid:
        assert row["implied_fcf_cagr"]["status"] == "ok"


def test_reverse_dcf_respects_custom_assumptions():
    out = compute_reverse_dcf(19_900_000_000, 600_000_000, {"discount_rate": 0.10, "terminal_growth": 0.02})
    assert out["assumptions"]["discount_rate"]["value"] == 0.10
    assert out["assumptions"]["discount_rate"]["type"] == "assumption"
    assert out["assumptions"]["terminal_growth"]["value"] == 0.02


def test_missing_or_nonpositive_fcf_is_unavailable_not_a_guess():
    assert solve_implied_growth(19_900_000_000, None, 0.09, 0.03, 10) is None
    assert solve_implied_growth(19_900_000_000, 0, 0.09, 0.03, 10) is None
    assert solve_implied_growth(19_900_000_000, -1, 0.09, 0.03, 10) is None
    out = compute_reverse_dcf(19_900_000_000, None)
    assert out["implied_fcf_cagr"]["status"] == "unavailable"
    assert out["implied_fcf_cagr"]["value"] is None


def test_discount_rate_must_exceed_terminal_growth():
    """Otherwise the Gordon-growth terminal value diverges; must not guess."""
    assert solve_implied_growth(19_900_000_000, 600_000_000, 0.03, 0.03, 10) is None
    assert solve_implied_growth(19_900_000_000, 600_000_000, 0.02, 0.03, 10) is None
