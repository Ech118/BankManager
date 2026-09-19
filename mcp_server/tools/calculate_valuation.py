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

Purpose: P/E, EV/EBITDA, EV/revenue, P/FCF, peer and historical multiples, and
the reverse DCF. The agent chooses the methods and the peers; code does the sums
and always returns a sensitivity grid rather than a single point (error D).

Errors: ValueError for an unknown method name.
as_of: NOT taken. This is a COMPUTE tool; the factsheet it works from already
carries the authoritative as_of, and a second date could silently disagree
(amendment 2).

TODO(roadmap Step 4, P1 + P2): wire to calc.api.calculate_valuation.
"""

from __future__ import annotations

from typing import Any

from schema.contracts.tools import CalculateValuationRequest, CalculateValuationResponse


def run(request: CalculateValuationRequest, backends: Any) -> CalculateValuationResponse:
    """Pass `request` to calc.api.calculate_valuation and return its answer.

    The entire body should stay this short.
    """
    raise NotImplementedError("TODO(roadmap Step 4, P1 + P2)")
