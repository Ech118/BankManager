# CONTRACT CHANGE: add a `get_factsheet` MCP tool

**From:** P1  **To:** P2, P3, coordinator  **Type:** additive
**Urgency:** blocks the real composition root. P3 is currently injecting a
factsheet from outside the pipeline to satisfy `audit.run_audit`.

## What

Add one request/response pair to `schema/contracts/tools.py`:

```python
class GetFactsheetRequest(DataToolRequest):   # ticker + the inherited as_of
    ticker: Ticker

class GetFactsheetResponse(ToolResponse):
    factsheet: Factsheet | None = None
```

registered as `"get_factsheet"` in `TOOL_REQUESTS` and `TOOL_RESPONSES`,
bringing the tool count from ten to eleven.

## Why

`audit.api.run_audit(state, factsheet, get_text, verify_claim)` requires a
`Factsheet`. P3 may not import `data/` (ADR 0007), and none of the ten existing
tools returns one — so there was no contract-described path from the thing that
produces a factsheet (P1) to the thing that consumes it (P2), and P3 bridged the
gap by injection. Reported as item 2 of
`2026-09-19-p3-report-inputs.md`; answered in
`2026-09-19-p3-report-inputs-response.md`.

The alternative considered was changing what `run_audit` needs — an injected
fact resolver rather than a factsheet. Rejected: it would let the auditor check
facts the agents never saw, and the value of auditing against a factsheet is
that it is the same frozen picture the run reasoned from.

## Why this is additive

- A new tool. Every existing tool's shape is untouched.
- No field is added to, removed from or retyped on any existing model.
- Old readers keep working: a client that does not know `get_factsheet` simply
  never calls it, and `tools/list` gaining an entry is not a breaking change.
- `Factsheet` itself is unchanged — it is imported into `tools.py`, not edited.

Per CONTRIBUTING.md an additive change needs the producing partition's owner
(P1, the author) plus the coordinator.

## What it costs

`get_factsheet` assembles what the other tools return piecemeal and is the most
expensive call on the surface. It is documented as a composition-root and
auditor tool, not an agent tool. If an agent starts calling it per claim, that
is a prompt bug, and the fix is in `prompts/`, not here.

## Applied

Branch `contracts/get-factsheet-tool`, one commit:

- `schema/contracts/tools.py` — the pair, registered in both maps
- `make gen-schema` — `schema/tools.json` regenerated (no other schema moved)
- `make gen-mock` — fixtures regenerated; the only lines that changed are
  `schema_version`
- `SCHEMA_VERSION` 2.0.0 -> **2.1.0** (additive, so a minor bump).
  `STATE_VERSION` is untouched: the state shape did not move
- `schema/CHANGELOG.md` — 2.1.0 entry
- `tests/contracts/test_models.py` — the tool-count assertion 10 -> 11
- `docs/mcp-tools.md` — the tool documented

`make lint` and `make test-contracts` pass.

## Approvals

- [x] **P1** (producing partition) — author
- [ ] **Coordinator** — required for an additive change
- [ ] **P2** — FYI; `audit.run_audit`'s signature does not change
- [ ] **P3** — FYI; this removes the need for the injected `factsheet=`

---

## Also on this branch: `search_filing` will not use Postgres

Not a contract change — `SearchFilingRequest` and `SearchFilingResponse` are
untouched — but it contradicts the wording of
[ADR 0006](../adr/0006-no-naive-chunk-and-embed-rag.md), so it is recorded here
rather than left in a commit message.

ADR 0006 says search "starts as Postgres full-text search scoped by ticker,
form, item and date". The implementation will instead rank the already-extracted
sections with a keyword index held in process.

**What the ADR actually rules out is unchanged.** No chunking, no embeddings, no
fragment retrieval: the unit of retrieval is still a whole structural section,
still scoped by ticker, form, item and date, still deterministic and
inspectable. Only the index technology differs.

**Why.** A run reads one company's filings — a few hundred sections. A
process-local index over that is faster than a round trip, needs no service to
be running, and keeps the offline test suite genuinely offline. Postgres earns
its place when the corpus outgrows one company per run; the tool signature does
not change when it does.

`docs/mcp-tools.md#search_filing` now says this. **The ADR text itself has been
left alone** — amending an ADR is the coordinator's call, and a decision that
was made and then narrowed is better read as a note on the ADR than as a silent
rewrite of it. Coordinator: either amend ADR 0006 with a status note, or tell P1
to put Postgres back.
