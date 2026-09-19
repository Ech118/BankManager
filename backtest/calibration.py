"""The calibration chart: do stated probabilities match observed frequencies?

Specified by docs/roadmap.md Step 6.

Calibration asks whether, of the cases called 70% likely, about 70% happened.
A model can be well calibrated and useless (always saying 50%), or sharp and
badly calibrated, so the chart is reported alongside the Brier score.

THE SAMPLE-SIZE RULE. Below MIN_N_FOR_CALIBRATION the chart is labelled
"illustrative", in the image itself and not just in the caption. With twenty
tickers the bins hold two or three observations each and the curve is noise; a
chart that looks like evidence when it is not is worse than no chart.

TODO(roadmap Step 6, P2).
"""

from __future__ import annotations

from pathlib import Path

MIN_N_FOR_CALIBRATION = 100
"""Below this, the chart is labelled illustrative. Not negotiable in the demo."""

DEFAULT_BINS = 10


def calibration_bins(
    predictions: list[tuple[float, bool]], bins: int = DEFAULT_BINS
) -> list[dict]:
    """Group predictions by stated probability; return predicted vs observed."""
    raise NotImplementedError("TODO(roadmap Step 6, P2)")


def render_chart(bins: list[dict], n: int, out_path: Path) -> Path:
    """Render the reliability diagram.

    When n < MIN_N_FOR_CALIBRATION, stamp "ILLUSTRATIVE - n=<n>" across the plot
    area, so the caveat cannot be separated from the image.
    """
    raise NotImplementedError("TODO(roadmap Step 6, P2)")
