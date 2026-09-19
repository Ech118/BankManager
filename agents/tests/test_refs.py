from agents import refs
from agents.tests.helpers import make_ctx


def test_index_covers_factsheet_metrics_and_scenarios():
    ctx = make_ctx()
    idx = refs.build_index(ctx.factsheet, ctx.metrics)
    for path in ("market.price", "financials.FY2025.revenue", "metrics.margins.FY2025.gross",
                 "metrics.reverse_dcf.implied_fcf_cagr", "sp500_baseline.forward_pe", "peers.PRAA.pe"):
        assert path in idx, path


def test_resolve_returns_real_value_objects_not_copies_of_llm_text():
    ctx = make_ctx()
    found, missing = refs.resolve(["metrics.margins.FY2025.gross", "metrics.nope", "metrics.margins.FY2025.gross"], ctx.index)
    assert len(found) == 1 and found[0]["value"] == 0.4 and found[0]["derived_from"]
    assert missing == ["metrics.nope"]
    found[0]["value"] = 999
    assert ctx.index["metrics.margins.FY2025.gross"]["value"] == 0.4   # deep copy


def test_table_lists_values_units_and_types():
    ctx = make_ctx()
    table = refs.format_table(ctx.index, ("metrics.margins.FY2025",))
    assert "metrics.margins.FY2025.gross = 0.4 (fraction, fact)" in table
