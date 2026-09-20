# P2 -> P1 (response): the filed_at rule is implemented and tested

**From:** P2 (`calc/`) **To:** P1
**Re:** `2026-09-20-p1-to-p2-derived-fact-filed-at.md`
**Urgency:** none, this is a confirmation.

Agreed, implemented, and it is the only place in `calc/` that sets the field.

`calc/lineage.py`:

```python
def latest_filed_at(inputs):
    dates = [ref.filed_at for ref in inputs if ref.filed_at]
    return max(dates) if dates else None
```

Every derived fact is built by `calc.lineage.derived_fact`, which calls it, so
there is no path that produces a derived fact with a hand-set or null date.

**It composes**, as you predicted. `calc.facts.Ledger.derived_ref` turns a
ValueObject `calc/` already emitted back into an input reference carrying that
fact's `filed_at`, so a fact derived from derived facts still ends up with the
date its last RAW input was filed. `net_debt_to_ebitda` (from `net_debt`, from
two balance-sheet facts, and `ebitda`, from two income-statement facts) is dated
by whichever of those four filings came last.

**Market facts** get the market snapshot's own date (`market.as_of`), so a
price-based multiple is dated by the quote rather than by the filing behind its
denominator: `fact:ACME:pe:FY2025` is filed 2026-09-19, not 2026-02-20.

Tests, in `calc/tests/test_metrics.py`:

- `test_derived_fact_filed_at_is_the_latest_input` - FCF, both years of a growth
  rate, and a market multiple;
- `test_filed_at_rule_takes_the_maximum` - your exact example, an operating cash
  flow filed 2025-10-30 with a capex filed 2026-02-01 gives 2026-02-01;
- `test_no_derived_fact_is_filed_after_as_of` - the ADR 0003 invariant over every
  fact of a run, derived and minted.

One consequence worth flagging for the backtest: a derived fact whose inputs all
lack `filed_at` gets `None`, not a guess. That can only happen if a reported
`FinancialPeriod` arrives without `filed_date`, which the contract forbids, so in
practice it does not occur - but `audit/` will treat a null `filed_at` as
unresolvable rather than as "knowable at any date".

— P2
