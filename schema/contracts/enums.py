"""Closed vocabularies shared by every partition.

Specified by docs/data-model.md and docs/research-state.md. Adding a member is an
ADDITIVE contract change; removing or renaming one is BREAKING (CONTRIBUTING.md).
"""

from __future__ import annotations

from enum import StrEnum


class Mode(StrEnum):
    """How a run obtained its data. `backtest` implies a non-null as_of."""

    LIVE = "live"
    MOCK = "mock"
    BACKTEST = "backtest"


class Unit(StrEnum):
    """Unit of a ValueObject. `fraction` is never a percent (0.25 means 25%)."""

    USD = "usd"
    USD_PER_SHARE = "usd_per_share"
    SHARES = "shares"
    FRACTION = "fraction"
    MULTIPLE = "multiple"
    COUNT = "count"
    DAYS = "days"
    RATIO = "ratio"


class ValueType(StrEnum):
    """Epistemic status of a number, rendered as a colour in the report.

    fact       reported in a filing, or computed in code from reported values
    estimate   a forecast: consensus, or a scenario output
    assumption a chosen constant: discount rate, terminal growth, exit multiple
    """

    FACT = "fact"
    ESTIMATE = "estimate"
    ASSUMPTION = "assumption"


class ValueStatus(StrEnum):
    """`unavailable` is the ONLY way to express missing data. Never 0, never "N/A"."""

    OK = "ok"
    UNAVAILABLE = "unavailable"


class PeriodType(StrEnum):
    """XBRL period shape. `duration` spans a range; `instant` is a point in time."""

    DURATION = "duration"
    INSTANT = "instant"


class FilingType(StrEnum):
    TEN_K = "10-K"
    TEN_Q = "10-Q"
    EIGHT_K = "8-K"


class ItemCode(StrEnum):
    """Canonical filing sections. Parsed by structure, never chunk-and-embed (ADR 0006)."""

    BUSINESS = "business"
    RISK_FACTORS = "risk_factors"
    MDNA = "mdna"
    FINANCIAL_STATEMENTS = "financial_statements"
    DEBT_NOTE = "debt_note"
    SBC_NOTE = "sbc_note"
    SEGMENTS_NOTE = "segments_note"
    REVENUE_NOTE = "revenue_note"
    CONTROLS = "controls"
    OTHER = "other"


class SourceKind(StrEnum):
    """Where a FinancialFact came from. `derived` REQUIRES a Derivation."""

    XBRL_REPORTED = "xbrl_reported"
    DERIVED = "derived"
    FILING_TEXT = "filing_text"
    MARKET_API = "market_api"
    ESTIMATE = "estimate"


class DerivedBy(StrEnum):
    """Who produced a Claim. `code` claims may carry numbers computed in calc/."""

    CODE = "code"
    AGENT = "agent"
    FILING_TEXT = "filing_text"


class AgentName(StrEnum):
    """The P3 agent roster (docs/pipeline.md).

    financial and business run in parallel; valuation, then scenario, then
    red_team, then synthesizer. `verifier` is the LLM half of audit/.
    """

    FINANCIAL = "financial"
    BUSINESS = "business"
    VALUATION = "valuation"
    SCENARIO = "scenario"
    RED_TEAM = "red_team"
    SYNTHESIZER = "synthesizer"
    VERIFIER = "verifier"


class ScenarioName(StrEnum):
    BEAR = "bear"
    BASE = "base"
    BULL = "bull"


class Horizon(StrEnum):
    """The three forecast horizons. Keys match `Scores` so returns and scores align.

    Use HORIZON_LABELS for display and HORIZON_YEARS for arithmetic.
    """

    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"


HORIZON_LABELS: dict[Horizon, str] = {
    Horizon.SHORT_TERM: "0-12m",
    Horizon.MEDIUM_TERM: "1-3y",
    Horizon.LONG_TERM: "3-5y",
}
"""Display labels. The report renders these, never the raw enum keys."""

HORIZON_YEARS: dict[Horizon, float] = {
    Horizon.SHORT_TERM: 1.0,
    Horizon.MEDIUM_TERM: 3.0,
    Horizon.LONG_TERM: 5.0,
}
"""Years used when annualizing. calc/ is the only place that may use these."""


class Trend(StrEnum):
    """Whether a finding reflects a durable change or a passing one."""

    STRUCTURALLY_POSITIVE = "structurally_positive"
    TEMPORARILY_POSITIVE = "temporarily_positive"
    STRUCTURALLY_NEGATIVE = "structurally_negative"
    TEMPORARILY_NEGATIVE = "temporarily_negative"
    NEUTRAL = "neutral"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Severity(StrEnum):
    """Verification issue severity. A single `error` fails the whole audit."""

    ERROR = "error"
    WARN = "warn"


class FlagSeverity(StrEnum):
    """Earnings-quality flag severity raised by calc/. Informational, never fatal."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class VerificationStatus(StrEnum):
    """Lifecycle of a Claim through the verification gate (docs/verification.md).

    unverified is the terminal state for a claim that failed after the retry cap;
    the report ships with it marked, rather than being blocked.
    """

    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    UNVERIFIED = "unverified"


class IssueType(StrEnum):
    """Every check the verifier can raise. Routing table: docs/verification.md.

    unresolved_fact            a cited fact_id does not exist
    recompute_mismatch         a number does not match recomputation from its inputs
    prose_number_mismatch      a number in claim text disagrees with its ValueObject
    superseded_fact            a cited fact has a non-null superseded_by
    future_fact                a cited fact was filed after the run's as_of
    adjusted_as_gaap           a non-GAAP figure is presented as GAAP
    unsupported_claim          a qualitative claim's quote is not in the cited section
    cross_agent_contradiction  two sections assert incompatible things
    """

    UNRESOLVED_FACT = "unresolved_fact"
    RECOMPUTE_MISMATCH = "recompute_mismatch"
    PROSE_NUMBER_MISMATCH = "prose_number_mismatch"
    SUPERSEDED_FACT = "superseded_fact"
    FUTURE_FACT = "future_fact"
    ADJUSTED_AS_GAAP = "adjusted_as_gaap"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    CROSS_AGENT_CONTRADICTION = "cross_agent_contradiction"


DETERMINISTIC_ISSUE_TYPES: frozenset[IssueType] = frozenset(
    {
        IssueType.UNRESOLVED_FACT,
        IssueType.RECOMPUTE_MISMATCH,
        IssueType.PROSE_NUMBER_MISMATCH,
        IssueType.SUPERSEDED_FACT,
        IssueType.FUTURE_FACT,
        IssueType.ADJUSTED_AS_GAAP,
        IssueType.CROSS_AGENT_CONTRADICTION,
    }
)
"""Checks that are pure code. Only UNSUPPORTED_CLAIM needs an LLM (ADR 0005)."""

LLM_ISSUE_TYPES: frozenset[IssueType] = frozenset({IssueType.UNSUPPORTED_CLAIM})
"""Checks that require an LLM. Kept as small as possible on purpose."""
