"""Shared contracts for BankManager. SOURCE OF TRUTH for every cross-partition shape.

Owned jointly by P1, P2 and P3 (see CONTRIBUTING.md "Contract change process").
Changing anything here is a CONTRACT-CHANGE PR: it needs approval from all three
partitions and a `schema/CHANGELOG.md` entry.

The pydantic models in this package are authoritative. The JSON Schema files in
`schema/*.json` are GENERATED from them by `make gen-schema`
(`schema/contracts/export.py`); `tests/contracts/test_schema_export.py` fails if
the committed JSON drifts from the models.

Conventions enforced here (docs/data-model.md, CLAUDE.md "Conventions"):
  - Fractions, never percents. 0.25 means 25%.
  - Money in full USD units. `scale` records what a filing reported; `value` is
    always already normalized to full units.
  - ISO 8601 dates (YYYY-MM-DD) and UTC timestamps.
  - Missing data is {"value": null, "status": "unavailable"} - never 0.
  - Every reported or computed financial number is a ValueObject carrying
    provenance; Claims cite fact_ids, never bare numbers.
"""

from schema.contracts.analysis import Analysis, Finding
from schema.contracts.claims import Claim
from schema.contracts.common import (
    DataQuality,
    Evidence,
    Scope,
    SourceRef,
    ValueObject,
)
from schema.contracts.enums import (
    AgentName,
    Confidence,
    DerivedBy,
    FilingType,
    FlagSeverity,
    Horizon,
    IssueType,
    ItemCode,
    Mode,
    PeriodType,
    ScenarioName,
    Severity,
    SourceKind,
    Trend,
    Unit,
    ValueType,
    VerificationStatus,
)
from schema.contracts.facts import Derivation, FinancialFact
from schema.contracts.factsheet import Factsheet, FinancialPeriod
from schema.contracts.filings import Filing, FilingSection
from schema.contracts.market import CompanyProfile, MarketSnapshot, NewsItem, Peer
from schema.contracts.metrics import Metrics, QualityFlag, ReverseDcf, SensitivityRow
from schema.contracts.scenario_result import (
    Consistency,
    Prior,
    ScenarioOut,
    ScenarioResult,
    ScenarioWeights,
    Scores,
    WeightClamp,
)
from schema.contracts.scenarios import PriorShift, Scenario, Scenarios
from schema.contracts.state import (
    STATE_VERSION,
    ResearchSection,
    ResearchSections,
    ResearchState,
)
from schema.contracts.verdict import ReportSection, Verdict, VerdictCard
from schema.contracts.verification import (
    RetryDirective,
    VerificationIssue,
    VerificationResult,
)

SCHEMA_VERSION = "2.1.0"
"""Semantic version of the whole contract set. Bumped on breaking changes only."""

__all__ = [
    "SCHEMA_VERSION",
    "STATE_VERSION",
    "AgentName",
    "Analysis",
    "Claim",
    "CompanyProfile",
    "Confidence",
    "Consistency",
    "DataQuality",
    "Derivation",
    "DerivedBy",
    "Evidence",
    "Factsheet",
    "Filing",
    "FilingSection",
    "FilingType",
    "FinancialFact",
    "FinancialPeriod",
    "Finding",
    "FlagSeverity",
    "Horizon",
    "IssueType",
    "ItemCode",
    "MarketSnapshot",
    "Metrics",
    "Mode",
    "NewsItem",
    "Peer",
    "PeriodType",
    "Prior",
    "PriorShift",
    "QualityFlag",
    "ReportSection",
    "ResearchSection",
    "ResearchSections",
    "ResearchState",
    "RetryDirective",
    "ReverseDcf",
    "Scenario",
    "ScenarioName",
    "ScenarioOut",
    "ScenarioResult",
    "ScenarioWeights",
    "Scenarios",
    "Scope",
    "Scores",
    "SensitivityRow",
    "Severity",
    "SourceKind",
    "SourceRef",
    "Trend",
    "Unit",
    "ValueObject",
    "ValueType",
    "Verdict",
    "VerdictCard",
    "VerificationIssue",
    "VerificationResult",
    "VerificationStatus",
    "WeightClamp",
]
