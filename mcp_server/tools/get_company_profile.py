"""MCP tool: get_company_profile. Wraps data.api.get_company_profile.

Specified by docs/mcp-tools.md#get_company_profile.

Purpose: identity, SIC classification and fiscal year end. The fiscal year end
matters more than it looks: it decides how periods are labelled and how Q4 is
derived (docs/sec-pitfalls.md).

Errors: ValueError for an out-of-scope ticker.
as_of: required.
"""

from __future__ import annotations

from typing import Any

from mcp_server.backends import require_in_scope
from schema.contracts.tools import GetCompanyProfileRequest, GetCompanyProfileResponse


def run(request: GetCompanyProfileRequest, backends: Any) -> GetCompanyProfileResponse:
    require_in_scope(request.ticker, request.as_of)

    profile = backends.market.get_profile(request.ticker, request.as_of)

    return GetCompanyProfileResponse(as_of=request.as_of, profile=profile)
