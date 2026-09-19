"""Unit tests for backtest.grade and backtest.calibration (plan.txt 15.14 P2
step 7: grader + calibration chart labelled 'illustrative' unless N >= 100,
error B)."""
import json
from pathlib import Path

import pytest

from backtest.calibration import compute_calibration, render_calibration_svg
from backtest.grade import grade_case

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "mock"


def load_verdict():
    return json.loads((FIXTURES / "verdict.json").read_text())


def test_grade_case_flags_beat_and_miss():
    verdict = load_verdict()
    beat = grade_case("ACME", "2025-06-01", verdict, realized_annualized_return=0.20)
    assert beat["beat_sp500"] is True
    miss = grade_case("ACME", "2025-06-01", verdict, realized_annualized_return=0.01)
    assert miss["beat_sp500"] is False


def test_grade_case_brier_component_rewards_confident_correct_predictions():
    verdict = load_verdict()  # ACME predicts p_beat_sp500_5y = 0.32 (bearish)
    beat = grade_case("ACME", "2025-06-01", verdict, realized_annualized_return=0.20)
    miss = grade_case("ACME", "2025-06-01", verdict, realized_annualized_return=0.01)
    # ACME's low p_beat_sp500 is a better bet when the stock actually misses.
    assert miss["brier_component"] < beat["brier_component"]


def test_calibration_is_illustrative_below_100_cases():
    verdict = load_verdict()
    cases = [grade_case("ACME", "2025-06-01", verdict, realized_annualized_return=r)
             for r in (0.20, 0.01, -0.05, 0.30, 0.02)]
    cal = compute_calibration(cases)
    assert cal["n"] == 5
    assert cal["illustrative"] is True


def test_calibration_is_not_illustrative_at_100_cases():
    verdict = load_verdict()
    cases = [grade_case("ACME", "2025-06-01", verdict, realized_annualized_return=0.05) for _ in range(100)]
    cal = compute_calibration(cases)
    assert cal["illustrative"] is False


def test_calibration_bins_report_mean_predicted_and_actual_frequency():
    verdict = load_verdict()
    cases = [grade_case("ACME", "2025-06-01", verdict, realized_annualized_return=r)
              for r in (0.20, 0.01, -0.05, 0.30, 0.02)]
    cal = compute_calibration(cases, n_bins=5)
    populated = [b for b in cal["bins"] if b["n"] > 0]
    assert populated
    for b in populated:
        assert 0.0 <= b["mean_predicted"] <= 1.0
        assert 0.0 <= b["actual_frequency"] <= 1.0


def test_render_calibration_svg_labels_illustrative_and_is_valid_svg():
    verdict = load_verdict()
    cases = [grade_case("ACME", "2025-06-01", verdict, realized_annualized_return=r)
             for r in (0.20, 0.01, -0.05)]
    cal = compute_calibration(cases)
    svg = render_calibration_svg(cal)
    assert svg.strip().startswith("<svg")
    assert svg.strip().endswith("</svg>")
    assert "ILLUSTRATIVE" in svg


def test_empty_case_list_does_not_crash():
    cal = compute_calibration([])
    assert cal["n"] == 0
    assert cal["illustrative"] is True
    assert cal["brier_score"] is None
    svg = render_calibration_svg(cal)
    assert "<svg" in svg
