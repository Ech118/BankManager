"""P1 normalization: raw provider payloads -> FinancialFact rows.

Specified by docs/data-model.md and docs/sec-pitfalls.md.

This is where every SEC-specific trap is handled once, so that no agent and no
calculation ever has to know about them: concept tag variance, dimensioned vs
consolidated facts, year-to-date cash flow, the missing Q4, and restatements.
"""
