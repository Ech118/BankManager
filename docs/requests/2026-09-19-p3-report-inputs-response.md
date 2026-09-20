# P1 -> P3: response to "three gaps found while building Roadmap Step 2"

**From:** P1 (data & MCP)  **Re:** `2026-09-19-p3-report-inputs.md`
**Answers:** items 2 and 3. Item 1 is P3's own `ResearchState` convention and
needs the coordinator, not P1.

---

## Item 2 — nothing on the MCP surface yields a `Factsheet`

**Answer: a `get_factsheet` MCP tool, not a change to `run_audit`.**

Proposed as a contract change in
`2026-09-20-p1-to-all-get-factsheet-tool.md` and applied on
`contracts/get-factsheet-tool`.

```
get_factsheet(ticker, as_of) -> {"factsheet": Factsheet | null, "as_of": ...}
```

**What P3 should do.** Drop the injected `factsheet=` callable from the
composition root and fetch it over MCP like every other input:

```python
result = await client.call_tool("get_factsheet", {"ticker": t, "as_of": as_of})
factsheet = result.structured_content["factsheet"]
audit.run_audit(state, factsheet, get_text, verify_claim)
```

Keeping the injection point as a test seam is fine and probably wise — P3's
stub factsheets stay useful. What changes is that the *real* run no longer needs
anyone outside the pipeline to hand P1's artifact to P2's auditor.

**Why a tool rather than loosening `run_audit`.** The alternative on the table
was to give the auditor an injected resolver instead of a factsheet. That trades
one object for a stream of callbacks, and it would let the auditor check facts
that the agents never saw — the whole point of auditing against a factsheet is
that it is the same frozen picture the run reasoned from. A tool keeps that
property and costs one call.

**`sp500_baseline` is covered by this too.** P3 correctly noted it has no tool of
its own. It does not need one: it is a field on the `Factsheet`, and P1 fills it
(SPY level and price from the market provider as `market_api`; the equity
risk-premium input as a documented `estimate`). It is never left unfilled.

**Cost warning.** `get_factsheet` assembles what the other tools return
piecemeal and is the most expensive call in the set. Call it once per run, in
the composition root. An agent that wants three numbers should still call
`get_financial_facts`.

---

## Item 3 — derived facts have no `filed_at`

**Answer: `filed_at` on a derived fact is the LATEST `filed_at` among its
inputs, set at creation time. It is never null.**

```
derived.filed_at = max(input.filed_at for input in derivation.inputs)
```

**Why the maximum and not the minimum.** A derived value did not exist until its
last input was filed. FCF for FY2025 built from an operating cash flow filed
2025-10-30 and a capex filed 2026-02-01 was not knowable on 2025-12-01, and a
run dated then must not see it. The maximum is the first date on which every
input was public, which is exactly the date the derived number became
knowable. The minimum would leak a future number into a past run — the failure
ADR 0003 exists to prevent.

**Why not null.** P3's double treats null as "always visible, its inputs were
already filtered". That holds only while the filter and the derivation run in
the same pass. As soon as a derived fact is cached, recorded to a fixture, or
read back by `resolve_fact` with a different `as_of` — all three of which now
happen — the assumption silently stops holding and the fact becomes visible in
runs that predate its inputs. A real date is checkable by the same comparison as
every other fact, so no consumer needs a special case.

**Where it is applied in P1.** Every derived fact `data/` emits: total debt
(from its component facts), and the split-adjusted EPS and share counts (from
the as-filed fact and the split-ratio fact, so the ratio's filing date usually
wins). `data/tests/test_normalize.py` asserts the rule, including the case where
the ratio was filed after the value it adjusts.

**P2: this applies to `calc/` too.** Any fact `calc/` derives — FCF, margins,
per-share figures — should carry the same rule, so that
`max(inputs)` composes: a fact derived from derived facts still gets the date
its last raw input was filed. If `calc/` leaves `filed_at` null on its outputs,
the verifier's point-in-time check cannot see them and a backtest silently
includes numbers that did not exist. Filed separately for P2 as
`2026-09-20-p1-to-p2-derived-fact-filed-at.md`.

**`resolve_fact` and `is_future`.** With a real `filed_at`, `is_future` for a
derived fact is the ordinary `filed_at > as_of` comparison and needs no
special-casing. P3's request asked for `is_future` to be computed from the
inputs — that is what `max(inputs)` already encodes, once, at creation, rather
than on every resolve.
