"""The base-rate prior for P(beat S&P), and the cap on moving it.

Specified by docs/pipeline.md and docs/adr/0001 (plan review error C).

WHY A PRIOR AT ALL. Asked directly, a language model will produce a
confident-sounding probability that a stock beats the index, and that number
will move between runs on the same inputs. Anchoring on the historical base rate
(~40-45% over five years, because index returns concentrate in a few big
winners) and letting agents move it only within a capped range turns an
invention into an adjustment that has to be argued for.

WHO MAY REQUEST A SHIFT. The Scenario Agent and the Red Team, each with a
written reason. Their requests SUM, and the sum is capped. The Red Team's shift
is always downward in practice, which is the point: something in the pipeline
should be able to argue the verdict down.

Requested and applied are recorded separately, so an overruled agent stays
visible in the output.

TODO(roadmap Step 2, P2).
"""

from __future__ import annotations

from schema.contracts.scenario_result import Prior
from schema.contracts.scenarios import PriorShift


def base_rate() -> dict[str, float]:
    """Historical P(beat S&P) per horizon, from config.BASE_RATE_P_BEAT_SP500."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def apply_shifts(shifts: list[PriorShift]) -> Prior:
    """Sum the requested shifts, cap the total, record requested vs applied.

    The cap is symmetric and absolute: |applied| <= cap, and |applied| may never
    exceed |requested| (code may shrink a request, never enlarge it).
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def p_beat_sp500(prior: Prior) -> dict[str, float]:
    """Base rate plus the applied shift, clipped to [0, 1], per horizon."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")
