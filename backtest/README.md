# backtest/ — P2

**Owner: P2.** Rules: [docs/p2/CLAUDE.md](../docs/p2/CLAUDE.md).
Delivered at [roadmap](../docs/roadmap.md) Step 6.

## The problem this package cannot fully solve

The model's training data already contains what happened to most public
companies. Running the pipeline on a 2022 filing and finding it "predicted" 2023
proves very little — the model may simply remember. This is the single biggest
threat to the validity of any result here, so it is stated first.

Three defences, none sufficient alone:

1. **Point-in-time data** — no fact filed after `as_of` is visible
   ([ADR 0003](../docs/adr/0003-point-in-time-correctness.md)). Handled by P1.
2. **Anonymization** — `anonymize.py` strips the company name, ticker, product
   names and absolute dates before any agent sees the text. Passed to
   `orchestrator.run_analysis` as the `redact` hook.
3. **Forward paper trading** — [`predictions/`](../predictions/) logs dated
   predictions made today and graded later. The only one training data cannot
   contaminate, and therefore the most trustworthy.

**The demo must say which was used.**

## Two rules that keep results honest

- Graded on **excess return over the index**, never absolute return. A stock up
  15% in a year the index rose 25% was a bad call.
- A calibration chart from fewer than **100** tickers is stamped
  `ILLUSTRATIVE` *in the image*, not just in the caption. At twenty tickers the
  bins hold two or three observations each and the curve is noise.

## Layout

```
anonymize.py    the redact hook: name, ticker, products, absolute dates
harness.py      runs orchestrator.run_analysis with as_of + redact
grade.py        realized excess return, Brier score
calibration.py  reliability diagram, with the sample-size stamp
```

`harness.py` goes through `orchestrator.api.run_analysis` like any live run, so
a backtest exercises the real pipeline rather than a parallel one that could
drift away from it.
