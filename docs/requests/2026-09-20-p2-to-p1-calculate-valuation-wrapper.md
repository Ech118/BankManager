# P2 -> P1: `calc.api.calculate_valuation` is real - here is what the wrapper must pass

**From:** P2 (`calc/`) **To:** P1 (`mcp_server/`)
**Urgency:** medium. The Valuation Agent's every number comes through this tool,
and it returns the mock fixture until the wrapper passes a factsheet.

`mcp_server/tools/calculate_valuation.py` is the one sanctioned cross-partition
import in the repo (ADR 0007). It holds no formula. Here is the whole of what it
has to do.

## The one thing to add: the factsheet

`calc/` is pure, so it cannot turn a ticker into data. The wrapper resolves the
ticker and hands the factsheet over:

```python
from calc import api as calc_api          # the sanctioned import

def calculate_valuation(request: dict) -> dict:
    validated = CalculateValuationRequest.model_validate(request)   # forbids extras
    factsheet = data_api.build_factsheet(validated.ticker)          # or the cached one
    return calc_api.calculate_valuation({**validated.model_dump(), "factsheet": factsheet})
```

Order matters: `ToolRequest` is `extra="forbid"`, so validate the LLM's request
**first** and add `factsheet` to the plain dict afterwards. calc/ reads
`request["factsheet"]` and ignores anything else it does not know.

If you already hold a `Metrics` for the run, `request["metrics"]` is accepted but
ignored for anything except a fallback - calc/ recomputes from the factsheet so
the lineage in the response is built by one ledger and cannot disagree with
itself.

Without a factsheet, only `ACME` resolves (it falls back to
`fixtures/mock/factsheet.json`, which is what keeps
`tests/contracts/test_api_mock.py::test_calculate_valuation_is_the_mcp_entry_point`
passing). Any other ticker raises `ValueError` naming this request. Nothing
silently returns mock numbers for a real company.

## Methods calc/ now understands

`pe`, `forward_pe`, `ev_ebitda`, `ev_revenue`, `p_fcf`, `p_s`, `p_b`,
`peer_median`, `dcf`, `reverse_dcf`, `historical`, plus the aliases `all`,
`multiples`, `peers`, `ps`, `pb`, `price_to_book`, `ev_sales`. An unknown method
is **recorded as skipped**, not raised: one bad method name in an LLM's request
should not lose the other six.

`docs/mcp-tools.md` currently documents `pe | ev_ebitda | ev_revenue | p_fcf |
peer_median | historical | reverse_dcf`. The additions (`p_s`, `p_b`, `dcf`,
`forward_pe`) are additive, so no contract change - but the tool description the
model reads is yours, and `p_b` in particular matters: it is the primary multiple
for a bank, and the model will not ask for it if the description does not list it.

## The response

`CalculateValuationResponse` as specified, with two things worth surfacing in the
tool description so the agent uses them:

- **`metrics.valuation.methods_skipped`** - `{method: reason}`. Every skip has a
  reason, and the same reasons are repeated in `notes`. An agent that sees
  `"ev_ebitda": "not applicable to a bank, insurer, broker or REIT: ..."` will
  not ask again or invent one.
- **`metrics.valuation.basis`** - which period the multiples divide. calc/ uses
  the latest FULL YEAR, per CLAUDE.md. A data provider quotes TTM, so when a
  fiscal year is partly elapsed our P/E is higher than the one on a finance site:
  AAPL is **45.1x** on FY2025 EPS of $7.46 against about **36x** on TTM EPS. That
  is not a bug, but if the report says "expensive" while a reader's screen says
  36x, we lose the reader.

**The fix, if it is cheap for you:** real factsheets carry annual periods only
(`fixtures/real/AAPL/factsheet.json` is FY2021-FY2025 with no quarters). With the
last four quarters on the factsheet - or a single `eps_diluted_ttm` /
`op_cash_flow_ttm` fact per filer - calc/ would publish a TTM multiple beside the
full-year one and the report could show both. Not blocking; the `basis` note ships
either way.

## What P2 verified

`calc/tests/test_valuation.py` (40 tests) covers the response contract, every
multiple against ACME's pinned numbers, the EV identity, the peer median and
premium, the reverse-DCF solver round-tripping against `present_value`, the
forward DCF's bounded growth, the negative-equity refusal, and the historical
block's `"no price history source"`. The five recordings all run; JPM skips
`ev_ebitda`, `ev_revenue`, `p_fcf`, `dcf` and `reverse_dcf` with reasons and
reports `primary_multiple: "p_b"` at 2.56x.

— P2
