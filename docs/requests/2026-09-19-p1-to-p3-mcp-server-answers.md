# P1 -> P3 / coordinator: answers on the MCP server, the SDK major, and derived facts

**From:** P1 (`data/`, `mcp_server/`)  **To:** P3, coordinator
**Answers:** `2026-09-19-p3-to-p1-mock-mcp-server.md`, `2026-09-19-mcp-sdk-major-version.md`,
and item 3 of `2026-09-19-p3-report-inputs.md`.

## 1. The server is live. Seven tools, over real MCP.

`mcp_server.server.build_server()` returns an SDK `Server` with these registered:

`search_filings`, `get_filing_section`, `get_financial_facts`,
`get_market_snapshot`, `get_company_profile`, `get_peer_companies`, `resolve_fact`

**Your two top asks, `search_filings` and `get_filing_section`, are in.** The
Financial and Business agents can run against the real server now.

`IMPLEMENTED_TOOLS` is the authoritative tuple — read it rather than assuming ten.
Arguments are validated with the contract request models and responses are the
contract response models, as you asked. 73 tests drive it through a real `Client`
over the in-memory transport.

`build_server(backend=None)` already takes the injected backend you asked for.
Passing one is how you serve fixtures or Postgres from the same server; omitting it
resolves the backend lazily from `MODE`, so importing the module touches no fixture
file until a tool is actually called.

`get_filing_section` matches the semantics your test double relies on: it errors
for an unknown `section_id` **and** for one filed after `as_of` (never an empty
result), and `max_chars` truncation moves `text`, `char_end` and `char_count`
together, so `char_end - char_start == char_count == len(text)` still holds. The
truncated result is re-validated rather than patched, which is what proves it.

**Not yet served:** `search_filing` (Postgres full-text search) and `search_news`.
`calculate_valuation` waits on P2.

## 2. Standardising on mcp 2.x. Pinned.

`mcp_server/requirements.txt` now says `mcp>=2,<3`. `mcp>=1.2` was unbounded, which
is why one clone resolved to 1.x and another to 2.x. Your dual-major support in
`orchestrator/mcp_client.py` can stay or go as you prefer; nothing in `mcp_server/`
needs 1.x now.

**On error masking — it does not apply here, and I verified it rather than assuming.**
Your note is right about the high-level decorator API. `mcp_server/server.py` uses the
**low-level** `mcp.server.lowlevel.Server` and constructs `CallToolResult` itself, so
the reason text is not replaced. Confirmed over a real client round trip:

```
get_company_profile: is_error=True
  text=['BANKX: Mock: financial institution (SIC 6022). Banks are out of scope for v1.']
```

Same for `get_financial_facts` and `get_market_snapshot`. The human-readable reason
reaches you intact, so you can re-raise it before any model call.

## 3. Derived facts with `filed_at: null` — already handled.

`data/repositories/fixture_facts.py::_effective_filed_at` gives a derived fact the
**latest `filed_at` of the facts it was computed from**. So `fact:ACME:fcf:FY2025`
becomes visible exactly when its last input had been filed, never earlier.

Treating `null` as always-visible (what your test double does) is the one case that
can leak: a derived value whose inputs post-date `as_of` would show up in a backtest.
The real server does not do that, so expect a behaviour difference here — mine is the
stricter of the two.

`resolve_fact` flags `is_superseded` and `is_future` independently, and `is_future`
for a derived fact is computed from that same effective date.

## 4. The injection boundary question — my view, coordinator decides

You listed three options. **I recommend option 1**, a composition-root script owned by
neither partition.

Option 3 (stdio in mock too) is the easiest, but it contradicts `docs/mcp-tools.md`,
which makes in-memory-in-mock a deliberate choice: mock runs go through the same
dispatch and validation as live ones, so wiring mistakes surface offline rather than
during a demo. Paying ~1s of subprocess startup to lose that seems like the wrong
trade. Option 2 spends a new ADR and a second sanctioned import on something a
composition root gives us for free.

None of this blocks you: `InMemoryMcpClient(server)` already takes the server injected,
so whoever writes the composition root hands it `build_server()` and your code does not
change either way.

## 5. Still open, not mine to close

- **`build_factsheet` is still the ACME fixture.** Your auditor needs a real one; that
  is my Step 6. Until then the composition root has to hand you a factsheet, as you
  have it now.
- **`get_factsheet` as an MCP tool** (your report-inputs item 2) is a contract change.
  I have no objection to adding it, but it needs the CONTRACT-CHANGE PR and all three
  partitions, so I am not doing it unilaterally.
- **`make test` still fails to collect** — six identically-named `test_placeholders.py`
  modules, in `agents/`, `audit/`, `calc/`, `data/`, `orchestrator/` and `tests/e2e/`.
  I added `data/tests/__init__.py`, which fixes mine; the other five are not my files.
  Already filed as `2026-09-19-p1-to-coordinator-make-test-collection.md`.
