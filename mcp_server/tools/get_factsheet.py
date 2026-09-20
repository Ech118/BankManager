"""MCP tool: get_factsheet. Wraps data.api.build_factsheet.

Specified by docs/mcp-tools.md#get_factsheet.

WHY THIS TOOL EXISTS
    `audit.run_audit(state, factsheet, get_text, verify_claim)` requires a
    `Factsheet`, and the orchestrator may not import `data/` (ADR 0007). Without
    a tool there was no contract-described path from the partition that produces
    a factsheet to the one that consumes it, so P3 was injecting one from
    outside the pipeline - which meant the object the auditor checked was not
    necessarily the one the tools had answered from. Reported as item 2 of
    docs/requests/2026-09-19-p3-report-inputs.md.

    The alternative was to give the auditor an injected fact resolver instead.
    Rejected: it would let the auditor check facts the agents never saw, and the
    value of auditing against a factsheet is that it is the same frozen picture
    the run reasoned from.

THE MOST EXPENSIVE CALL ON THE SURFACE
    It assembles what the other tools return piecemeal. It is a
    composition-root and auditor tool, not an agent tool: an agent that wants
    three numbers should call `get_financial_facts`. If an agent starts calling
    this per claim, that is a prompt bug, and the fix belongs in `prompts/`.

Errors: ValueError for an out-of-scope ticker. A `null` factsheet means the
ticker is in scope but has no reportable history - the two stay distinguishable.
as_of: required, and the returned Factsheet.as_of equals it.
"""

from __future__ import annotations

from typing import Any

from mcp_server.backends import require_in_scope
from schema.contracts.factsheet import Factsheet
from schema.contracts.tools import GetFactsheetRequest, GetFactsheetResponse


def run(request: GetFactsheetRequest, backends: Any) -> GetFactsheetResponse:
    require_in_scope(request.ticker, request.as_of)

    from data import api as data_api

    try:
        raw = data_api.build_factsheet(request.ticker, request.as_of)
    except data_api.NoReportableHistory:
        # In scope, but nothing was filed by as_of. That is the `null` case,
        # not a failure: an agent asking about a company that had not yet filed
        # should be told there is nothing to read, rather than handed an error
        # it cannot tell apart from a bad ticker. Caught narrowly on purpose -
        # a bare `except ValueError` here would turn a validation bug into
        # "this company has no data", which is the kind of error that gets
        # believed.
        return GetFactsheetResponse(as_of=request.as_of, factsheet=None)

    factsheet = Factsheet.model_validate(raw)
    return GetFactsheetResponse(as_of=request.as_of, factsheet=factsheet)
