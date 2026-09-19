"""P3: the pipeline runner, HTTP server and report generator.

Public interface: orchestrator/api.py. Specified by docs/pipeline.md.

Reaches data ONLY through MCP tools (docs/adr/0007). It imports neither data/
nor calc/; orchestrator/mcp_client.py is the single door, and it speaks the same
protocol in mock mode as in live mode.
"""
