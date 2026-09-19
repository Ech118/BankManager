"""ScenarioResult - calc/'s answer. Every probability and score in the product.

Specified by docs/pipeline.md. PRODUCED BY calc.api.evaluate_scenarios +
calc.api.derive_scores. CONSUMED BY the Synthesizer, audit/ and the report.

Two bounding mechanisms live here, and both must be AUDITABLE, not just applied:
  - `weights`: the Scenario Agent's requested bear/base/bull weights, clamped
    into a configured band around the defaults, then renormalized. Every clamp is
    recorded; a weight may never be silently dropped or silently altered.
  - `prior`: the base-rate prior for P(beat S&P), shifted by the agents' requests
    only within a hard cap, recording requested vs applied.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schema.contracts.common import (
    ISODate,
    Probability,
    SchemaVersion,
    Score,
    Ticker,
    ValueObject,
)
from schema.contracts.enums import ScenarioName

WEIGHT_TOLERANCE = 1e-9
"""Float slack when comparing recorded weights. Tighter than the 1e-6 sum check."""

DEFAULT_SCENARIO_WEIGHTS: dict[str, float] = {"bear": 0.30, "base": 0.50, "bull": 0.20}
"""Reference defaults. calc/config.py holds the live values; each WeightClamp
records the default and band it was actually bounded against."""

DEFAULT_WEIGHT_BAND = 0.15
"""Reference band. A requested weight may move at most this far from its default."""

DEFAULT_PRIOR_CAP = 0.15
"""Reference cap on the total prior shift."""


class HorizonValues(BaseModel):
    """A ValueObject per horizon. Keys match Scores so returns and scores align."""

    model_config = ConfigDict(extra="allow")

    short_term: ValueObject = Field(description="0-12m.")
    medium_term: ValueObject = Field(description="1-3y.")
    long_term: ValueObject = Field(description="3-5y.")


class HorizonProbabilities(BaseModel):
    """A bare probability per horizon (documented exception to the ValueObject rule)."""

    model_config = ConfigDict(extra="allow")

    short_term: Probability = Field(description="0-12m.")
    medium_term: Probability = Field(description="1-3y.")
    long_term: Probability = Field(description="3-5y.")


class WeightClamp(BaseModel):
    """Audit record for ONE scenario weight, from request to applied value.

    The pipeline is: requested -> clamped_to (band around default) -> applied
    (after renormalizing so the three weights sum to 1). Both steps are recorded
    separately so a reader can see whether the agent was overruled, or merely
    rescaled because another weight was overruled.
    """

    model_config = ConfigDict(extra="allow")

    scenario: ScenarioName
    requested: float = Field(ge=0.0, le=1.0, description="What the Scenario Agent asked for.")
    clamped_to: float = Field(ge=0.0, le=1.0, description="After the band clamp.")
    applied: float = Field(ge=0.0, le=1.0, description="After renormalization. Used in the EV.")
    default_weight: float = Field(ge=0.0, le=1.0, description="Configured default for this scenario.")
    band: float = Field(ge=0.0, le=1.0, description="Configured +/- band around the default.")
    was_clamped: bool = Field(description="True when the band overruled the request.")
    was_renormalized: bool = Field(description="True when rescaling changed the clamped value.")
    reason: str | None = Field(
        default=None, description="The agent's rationale for the requested weight."
    )

    @model_validator(mode="after")
    def _check_flags_match_the_numbers(self) -> WeightClamp:
        """A clamp must never be silent: the flags have to match what happened."""
        clamped = abs(self.clamped_to - self.requested) > WEIGHT_TOLERANCE
        if clamped != self.was_clamped:
            raise ValueError(
                f"{self.scenario.value}: was_clamped={self.was_clamped} but requested="
                f"{self.requested} and clamped_to={self.clamped_to}; a clamp must be recorded"
            )
        renormalized = abs(self.applied - self.clamped_to) > WEIGHT_TOLERANCE
        if renormalized != self.was_renormalized:
            raise ValueError(
                f"{self.scenario.value}: was_renormalized={self.was_renormalized} but "
                f"clamped_to={self.clamped_to} and applied={self.applied}"
            )
        return self

    @model_validator(mode="after")
    def _check_inside_band(self) -> WeightClamp:
        """Both the clamped and the applied weight must sit inside the band."""
        lo, hi = self.default_weight - self.band, self.default_weight + self.band
        for name, val in (("clamped_to", self.clamped_to), ("applied", self.applied)):
            if not (lo - WEIGHT_TOLERANCE <= val <= hi + WEIGHT_TOLERANCE):
                raise ValueError(
                    f"{self.scenario.value}: {name}={val} is outside the configured band "
                    f"[{lo:.4f}, {hi:.4f}] (default {self.default_weight}, band {self.band})"
                )
        return self


class ScenarioWeights(BaseModel):
    """The bounded weights actually used to compute expected value.

    Carries one WeightClamp per scenario, always all three, so that a reader can
    reconstruct exactly what the agent asked for and what code did with it.
    """

    model_config = ConfigDict(extra="allow")

    bear: float = Field(ge=0.0, le=1.0)
    base: float = Field(ge=0.0, le=1.0)
    bull: float = Field(ge=0.0, le=1.0)
    clamps: list[WeightClamp] = Field(
        min_length=3, max_length=3, description="One per scenario. Never fewer."
    )
    any_clamped: bool = Field(description="True when at least one weight was overruled.")
    renormalized: bool = Field(description="True when clamping forced a rescale.")

    @model_validator(mode="after")
    def _check_one_clamp_per_scenario(self) -> ScenarioWeights:
        seen = [c.scenario for c in self.clamps]
        if sorted(s.value for s in seen) != ["base", "bear", "bull"]:
            raise ValueError(
                f"clamps must cover bear, base and bull exactly once, got "
                f"{sorted(s.value for s in seen)}"
            )
        return self

    @model_validator(mode="after")
    def _check_applied_matches_clamps(self) -> ScenarioWeights:
        """The weights used must be the applied values recorded in the clamps."""
        by_name = {c.scenario.value: c.applied for c in self.clamps}
        for name, weight in (("bear", self.bear), ("base", self.base), ("bull", self.bull)):
            if abs(by_name[name] - weight) > WEIGHT_TOLERANCE:
                raise ValueError(
                    f"{name} weight {weight} does not match its recorded applied value "
                    f"{by_name[name]}"
                )
        return self

    @model_validator(mode="after")
    def _check_sums_to_one(self) -> ScenarioWeights:
        total = self.bear + self.base + self.bull
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"applied scenario weights must sum to 1.0, got {total}")
        return self

    @model_validator(mode="after")
    def _check_flags_match_clamps(self) -> ScenarioWeights:
        if self.any_clamped != any(c.was_clamped for c in self.clamps):
            raise ValueError(
                f"any_clamped={self.any_clamped} disagrees with the recorded clamps"
            )
        if self.renormalized != any(c.was_renormalized for c in self.clamps):
            raise ValueError(
                f"renormalized={self.renormalized} disagrees with the recorded clamps"
            )
        return self


class ScenarioOut(BaseModel):
    """One evaluated scenario: what the price would be, and what that returns."""

    model_config = ConfigDict(extra="allow")

    probability: Probability = Field(description="The APPLIED weight, after bounding.")
    price_target: ValueObject
    annualized_return: ValueObject


class Prior(BaseModel):
    """The base rate for P(beat S&P), and how far the agents were allowed to move it.

    Historically only about 40-45% of individual stocks beat the index over five
    years. Starting from that and capping the LLM's tilt is what stops
    P(beat S&P) from being a number the model simply made up (error C).
    """

    model_config = ConfigDict(extra="allow")

    base_rate: HorizonProbabilities
    requested_shift: float = Field(description="Sum of every agent's requested shift.")
    applied_shift: float = Field(description="After the cap. |applied| <= cap.")
    cap: float = Field(ge=0.0, le=1.0, description="Hard cap from calc/config.py.")
    shift_reasons: list[str] = Field(
        default_factory=list, description="One entry per requesting agent."
    )

    @model_validator(mode="after")
    def _check_cap_respected(self) -> Prior:
        if abs(self.applied_shift) > self.cap + 1e-12:
            raise ValueError(
                f"applied_shift {self.applied_shift} exceeds cap {self.cap}"
            )
        if abs(self.applied_shift) > abs(self.requested_shift) + 1e-12:
            raise ValueError(
                f"applied_shift {self.applied_shift} exceeds requested_shift "
                f"{self.requested_shift}; code may shrink a request, never enlarge it"
            )
        return self


class Scores(BaseModel):
    """Buyability 1..10 per horizon, from calc/'s fixed rubric (docs/p2 rubric)."""

    model_config = ConfigDict(extra="allow")

    short_term: Score = Field(description="0-12m.")
    medium_term: Score = Field(description="1-3y.")
    long_term: Score = Field(description="3-5y.")


class Consistency(BaseModel):
    """Whether score, P(beat S&P), expected return and verdict agree."""

    model_config = ConfigDict(extra="allow")

    ok: bool
    issues: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_ok_matches_issues(self) -> Consistency:
        if self.ok and self.issues:
            raise ValueError(f"consistency ok=True but {len(self.issues)} issues were recorded")
        return self


class ScenarioResult(BaseModel):
    """Everything calc/ derives from a Scenarios proposal plus the factsheet."""

    model_config = ConfigDict(extra="allow")

    schema_version: SchemaVersion
    ticker: Ticker
    as_of: ISODate

    scenarios: dict[ScenarioName, ScenarioOut]
    weights: ScenarioWeights = Field(
        description="Bounded weights used for expected value, with the full clamp record."
    )

    expected_annualized_return: ValueObject = Field(
        description="Weighted by the APPLIED weights, not the requested ones."
    )
    sp500_expected_return: ValueObject = Field(description="Assumed index return (assumption).")
    expected_return_vs_sp500: HorizonValues = Field(
        description="Expected return minus the index, per horizon."
    )
    excess_vs_sp500: HorizonValues
    p_beat_sp500: HorizonProbabilities
    prior: Prior
    scores: Scores
    consistency: Consistency

    @model_validator(mode="after")
    def _check_all_three_scenarios(self) -> ScenarioResult:
        missing = set(ScenarioName) - set(self.scenarios)
        if missing:
            raise ValueError(
                f"scenarios must contain bear, base and bull; missing "
                f"{sorted(m.value for m in missing)}"
            )
        return self

    @model_validator(mode="after")
    def _check_scenario_probabilities_are_the_applied_weights(self) -> ScenarioResult:
        """A reader must never see a probability that bypassed the bounding step."""
        applied = {"bear": self.weights.bear, "base": self.weights.base, "bull": self.weights.bull}
        for name, out in self.scenarios.items():
            if abs(out.probability - applied[name.value]) > WEIGHT_TOLERANCE:
                raise ValueError(
                    f"scenarios.{name.value}.probability {out.probability} is not the "
                    f"applied weight {applied[name.value]}; expected value would be "
                    "computed from an unbounded weight"
                )
        return self
