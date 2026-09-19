"""P1: the MCP server. The only surface P3 is allowed to touch.

Specified by docs/mcp-tools.md and docs/adr/0007.

Contains NO formulas and NO business logic. Nine tools are thin wrappers over
data/api.py; calculate_valuation is a thin wrapper over calc/api.py and is the
one sanctioned cross-partition import in the repo.
"""
