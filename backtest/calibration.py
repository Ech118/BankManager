"""Calibration chart data + a plain-SVG renderer (no plotting dependency,
plan.txt 15.14 P2 step 7). error B: "Calibration chart on a handful of
tickers is statistically meaningless ... label it 'illustrative' unless N >=
100 tickers."
"""
from __future__ import annotations

CALIBRATION_MIN_N_FOR_NON_ILLUSTRATIVE = 100


def compute_calibration(graded_cases: list[dict], n_bins: int = 5) -> dict:
    """graded_cases: output of grade.grade_case() for each backtested ticker.
    Buckets by predicted_p_beat_sp500_5y into n_bins equal-width bins and
    reports the actual beat-S&P frequency in each bin, plus a Brier score."""
    n = len(graded_cases)
    bins = []
    width = 1.0 / n_bins
    for i in range(n_bins):
        lo, hi = i * width, (i + 1) * width
        in_bin = [c for c in graded_cases
                  if lo <= c["predicted_p_beat_sp500_5y"] < hi or (i == n_bins - 1 and c["predicted_p_beat_sp500_5y"] == hi)]
        if in_bin:
            mean_predicted = sum(c["predicted_p_beat_sp500_5y"] for c in in_bin) / len(in_bin)
            actual_frequency = sum(1 for c in in_bin if c["beat_sp500"]) / len(in_bin)
        else:
            mean_predicted = None
            actual_frequency = None
        bins.append({"lo": lo, "hi": hi, "n": len(in_bin), "mean_predicted": mean_predicted,
                     "actual_frequency": actual_frequency})

    brier_score = sum(c["brier_component"] for c in graded_cases) / n if n else None

    return {
        "n": n,
        "illustrative": n < CALIBRATION_MIN_N_FOR_NON_ILLUSTRATIVE,
        "brier_score": brier_score,
        "bins": bins,
    }


def render_calibration_svg(calibration: dict, width: int = 480, height: int = 480) -> str:
    """Render the calibration data as a minimal, dependency-free SVG scatter
    plot against the perfect-calibration diagonal."""
    pad = 48
    plot_w, plot_h = width - 2 * pad, height - 2 * pad

    def px(x: float) -> float:
        return pad + x * plot_w

    def py(y: float) -> float:
        return height - pad - y * plot_h

    title = f"Calibration (N={calibration['n']})"
    if calibration["illustrative"]:
        title += " - ILLUSTRATIVE, N < 100"

    points = []
    for b in calibration["bins"]:
        if b["mean_predicted"] is None:
            continue
        r = 4 + min(20, b["n"])
        points.append(
            f'<circle cx="{px(b["mean_predicted"]):.1f}" cy="{py(b["actual_frequency"]):.1f}" '
            f'r="{r}" fill="#2563eb" fill-opacity="0.75" />'
        )

    brier = calibration["brier_score"]
    brier_label = f"Brier score: {brier:.3f}" if brier is not None else "Brier score: n/a"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" fill="#ffffff" />
  <text x="{pad}" y="24" font-size="16" font-family="sans-serif" fill="#111827">{title}</text>
  <text x="{pad}" y="{height - 12}" font-size="12" font-family="sans-serif" fill="#6b7280">{brier_label}</text>
  <line x1="{px(0):.1f}" y1="{py(0):.1f}" x2="{px(1):.1f}" y2="{py(1):.1f}" stroke="#9ca3af" stroke-dasharray="4,4" />
  <line x1="{px(0):.1f}" y1="{py(0):.1f}" x2="{px(0):.1f}" y2="{py(1):.1f}" stroke="#111827" />
  <line x1="{px(0):.1f}" y1="{py(0):.1f}" x2="{px(1):.1f}" y2="{py(0):.1f}" stroke="#111827" />
  <text x="{px(0.5):.1f}" y="{height - pad + 32}" font-size="12" font-family="sans-serif" fill="#374151" text-anchor="middle">predicted P(beat S&amp;P 500)</text>
  <text x="{pad - 32}" y="{py(0.5):.1f}" font-size="12" font-family="sans-serif" fill="#374151" text-anchor="middle" transform="rotate(-90 {pad - 32} {py(0.5):.1f})">actual frequency</text>
  {"".join(points)}
</svg>
'''
