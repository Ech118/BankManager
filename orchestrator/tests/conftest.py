"""Test setup: the MCP SDK logs every request at INFO, which drowns test output."""

import logging

logging.getLogger("mcp").setLevel(logging.WARNING)
