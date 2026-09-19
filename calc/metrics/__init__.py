"""Deterministic metric computation. Specified by docs/data-model.md "Metrics".

Pure functions over a Factsheet. Each returns ValueObjects carrying
`derived_from`, so every metric can be recomputed by the verifier.

Convention (CLAUDE.md): flow metrics use the latest FULL YEAR, balance-sheet
metrics use the latest reported balance sheet. Mixing a trailing-quarter
numerator with an annual denominator is a classic silent error, so the two
period choices are named separately in Metrics.
"""
