"""MCP tool: calculate_valuation. Wraps calc.api.calculate_valuation.

Specified by docs/mcp-tools.md#calculate_valuation and docs/adr/0007.

=========================================================================
THE ONE SANCTIONED CROSS-PARTITION IMPORT IN THE REPO.
mcp_server/ is P1. calc/ is P2. This module imports calc.api and nothing else
from P2, and it contains NO FORMULA OF ITS OWN.

Why it exists: agents must not do arithmetic (ADR 0001), so the only way for an
agent to obtain a valuation is to ask code for one. The MCP surface is the only
thing agents can reach, so exactly one compute tool has to live on it.

Why it is safe: the wrapper is a pass-through. If a calculation ever starts to
appear here, it belongs in calc/valuation/ instead. Reviewers should treat any
arithmetic in this file as a defect.
=========================================================================

Purpose: P/E, forward P/E, EV/EBITDA, EV/revenue, P/FCF, P/S, P/B, peer and
historical multiples, and both DCFs. The agent chooses the methods and the
peers; code does the sums and always returns a sensitivity grid rather than a
single point (error D).

Errors: ValueError for a ticker that cannot be resolved to a factsheet. An
unknown method name is recorded in `metrics.valuation.methods_skipped`, not
raised.
as_of: NOT taken. This is a COMPUTE tool; the factsheet it works from already
carries the authoritative as_of, and a second date could silently disagree
(amendment 2).

WHY THE WRAPPER TOUCHES A FACTSHEET AT ALL
    `calc/` is pure - no network, no database - so it cannot turn a ticker into
    data. The wrapper resolves the ticker and hands the factsheet over. That is
    the only thing it adds, and it is still not a formula.

    Order matters: `ToolRequest` is `extra="forbid"`, so the LLM's request is
    validated FIRST and `factsheet` is added to the plain dict afterwards.
    Validating a dict that already carried the factsheet would fail on the extra
    key. Specified by P2 in
    docs/requests/2026-09-20-p2-to-p1-calculate-valuation-wrapper.md.

WHY AN UNKNOWN METHOD IS NOT AN ERROR HERE
    calc/ records an unrecognised method as skipped, with its reason, rather
    than raising. One bad method name in an LLM's request should not lose the
    other six, and a skip the agent can read is worth more than a failed call it
    can only retry.
"""

from __future__ import annotations

from typing import Any

from mcp_server.backends import require_in_scope
from schema.contracts.tools import CalculateValuationRequest, CalculateValuationResponse


def run(request: CalculateValuationRequest, backends: Any) -> CalculateValuationResponse:
    """Resolve the ticker to a factsheet, then pass the request to calc/.

    The entire body stays this short on purpose. Arithmetic appearing here is a
    defect; it belongs in calc/valuation/.
    """
    from calc import api as calc_api  # the one sanctioned cross-partition import
    from data import api as data_api

    require_in_scope(request.ticker)

    # calc/ falls back to the ACME fixture when no factsheet is supplied, which
    # is what keeps the contract suite offline. Passing one explicitly for every
    # other ticker is what stops a real company quietly receiving mock numbers.
    factsheet = data_api.build_factsheet(request.ticker)

    payload = calc_api.calculate_valuation(
        {**request.model_dump(), "factsheet": factsheet}
    )
    return CalculateValuationResponse.model_validate(payload)
