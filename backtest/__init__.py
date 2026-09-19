"""P2: historical evaluation. Specified by docs/roadmap.md Step 6.

THE PROBLEM THIS PACKAGE CANNOT FULLY SOLVE, and must therefore be honest about:
the model's training data already contains what happened to most public
companies. Running the pipeline on a 2022 filing and finding it "predicted"
2023 proves very little, because the model may simply remember.

Three defences, none sufficient alone:
  1. POINT-IN-TIME DATA (P1, ADR 0003) - no fact filed after as_of is visible.
  2. ANONYMIZATION (anonymize.py) - strip the company name, ticker, product
     names and absolute dates before any agent sees the text.
  3. FORWARD PAPER TRADING (predictions/) - dated predictions made today and
     graded later, which no amount of training data can contaminate.

The demo must state which of these was used. A calibration chart from fewer than
about a hundred tickers is labelled "illustrative", because at that sample size
it is.
"""
