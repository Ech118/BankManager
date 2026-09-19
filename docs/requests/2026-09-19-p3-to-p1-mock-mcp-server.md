# P3 -> P1: the mock MCP server, and who injects it

**From:** P3 (agents / orchestrator)  **To:** P1 (`mcp_server/`)  **Urgency:** blocks Roadmap Step 1's
"mock end-to-end against the real mock MCP" (P3 has verified everything up to that seam).

## What P3 needs

`mcp_server.server.build_server(backend)` returning a working MCP server (the SDK's `FastMCP`/`Server`)
that serves, from the fixture backend in `MODE=mock`, at least these Step 1 tools:

`get_financial_facts`, `get_filing_section`, `search_filings`, `resolve_fact`,
`get_market_snapshot`, `get_company_profile`.

Every tool must validate its arguments with the contract request models and return the contract
response models (`schema/contracts/tools.py`).

## A reference to copy semantics from

P3 wrote a **test double** so it could exercise the real MCP protocol before this exists:
`tests/e2e/support/fake_mcp.py` (real `FastMCP`, fixture data, no imports of `data/`, `calc/` or
`mcp_server/`). The behaviour P3's tests rely on, and which the real server should match:

- **Point in time.** Nothing with `filed_at > as_of` is returned. `get_filing_section` raises (KeyError)
  for a section filed after `as_of`, rather than returning empty.
- **Restatements.** `get_financial_facts` excludes `superseded_by != null` rows unless
  `include_superseded=true`. `resolve_fact` returns the fact with `is_superseded` / `is_future` flags.
- **Truncation.** `get_filing_section(max_chars=N)` returns exactly N chars, `truncated=true`, and keeps
  `char_end - char_start == char_count == len(text)` (the `FilingSection` validator requires it).
- **Errors.** An out-of-scope ticker raises `ValueError` with a human-readable reason (P3 re-raises it
  before any model call).

Once your server exists, P3's `orchestrator/tests/test_mcp_client.py` and `tests/e2e/test_checkpoints.py`
can be pointed at it by swapping the injected server object (one line in a fixture).

## A boundary question (needs the coordinator + P1 to decide)

`docs/p3/CLAUDE.md` and ADR 0007 say P3 **may not import `mcp_server/`**, and say mock mode uses the
SDK's **in-memory** transport, which needs the server object **in the same process**. Those two rules
cannot both hold without someone injecting the server. P3 has implemented
`InMemoryMcpClient(server)` with the server **injected** (it raises a clear `McpServerUnavailable`
otherwise), so P3 stays clean. Options for who does the injecting in a real mock run:

1. A composition-root script owned by neither partition (e.g. under `scripts/`, coordinator-owned) that
   imports `mcp_server` and P3's coordinator and wires them together.
2. A second sanctioned import recorded in a new ADR (`orchestrator` -> `mcp_server.server.build_server`
   only).
3. Mock mode uses the **stdio** transport too (spawns `python -m mcp_server.server` with `MODE=mock`):
   no import needed, still real MCP, at ~1s startup. P3's `StdioMcpClient` already works against the
   test double.

P3 recommends option 3 unless the in-memory speed matters. Until decided, `orchestrator.api.run_analysis`
still returns the fixture verdict in mock mode (no fabricated pipeline result).

## Fixture gap noticed (coordinator-owned, P3 will handle)

`fixtures/mock/analysis_financial.json` cites facts (`gross_profit`, `receivables`, `sbc` for FY2025)
that are not in `fixtures/mock/facts.json`. P3's agent correctly ignores unknown fact ids and logs it.
P3, as coordinator, will extend the facts fixture in a follow-up so the mock run has zero warnings.
