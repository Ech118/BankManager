"""MCP tool: get_company_profile. Wraps data.api.get_company_profile.

Specified by docs/mcp-tools.md#get_company_profile.

Purpose: identity, SIC classification and fiscal year end. The fiscal year end
matters more than it looks: it decides how periods are labelled and how Q4 is
derived (docs/sec-pitfalls.md).

Errors: ValueError for an out-of-scope ticker.
as_of: required.

TODO(roadmap Step 3, P1).
"""

from __future__ import annotations

from typing import Any

from schema.contracts.tools import GetCompanyProfileRequest, GetCompanyProfileResponse


def run(request: GetCompanyProfileRequest, backends: Any) -> GetCompanyProfileResponse:
    raise NotImplementedError("TODO(roadmap Step 3, P1)")
