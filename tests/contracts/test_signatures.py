"""Freezes the api.py signatures. Changing one is a BREAKING change (plan.txt 15.11).
FROZEN (Step 0): only the coordinator edits this file, in the same commit that
changes the signature, after all three people agree."""
import inspect

from audit import api as audit_api
from calc import api as calc_api
from data import api as data_api
from orchestrator import api as orch_api

EXPECTED = {
    (data_api, "check_scope"): ["ticker"],
    (data_api, "build_factsheet"): ["ticker", "as_of=None"],
    (data_api, "list_sections"): ["ticker", "as_of=None"],
    (data_api, "get_section_text"): ["source_id"],
    (data_api, "get_xbrl"): ["ticker", "metric", "periods", "as_of=None"],
    (calc_api, "compute_metrics"): ["factsheet"],
    (calc_api, "reverse_dcf"): ["factsheet", "metrics", "assumptions=None"],
    (calc_api, "evaluate_scenarios"): ["scenarios", "factsheet", "metrics"],
    (calc_api, "derive_scores"): ["scenario_result"],
    (calc_api, "validate_consistency"): ["scenario_result", "verdict_card"],
    (audit_api, "run_audit"): ["factsheet", "metrics", "analyses", "verdict", "get_text"],
    (orch_api, "run_analysis"): ["ticker", "as_of=None", "redact=None"],
}


def _sig(fn):
    out = []
    for name, p in inspect.signature(fn).parameters.items():
        out.append(name if p.default is inspect.Parameter.empty else f"{name}={p.default!r}")
    return out


def test_api_signatures_are_frozen():
    for (module, name), expected in EXPECTED.items():
        assert _sig(getattr(module, name)) == expected, f"{module.__name__}.{name} signature changed"
