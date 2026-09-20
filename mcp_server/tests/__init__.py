"""Makes mcp_server.tests a package.

Without this, pytest imports mcp_server/tests/conftest.py under the bare name
`conftest`, where it shadows tests/contracts/conftest.py and breaks
`from conftest import ORIGINAL_MODE` in tests/contracts/test_live.py whenever
both suites are collected in one run.
"""
