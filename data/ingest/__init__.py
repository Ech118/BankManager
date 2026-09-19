"""P1 ingestion: raw fetching only. Nothing in here normalizes or computes.

Specified by docs/data-model.md "Ingestion" and docs/sec-pitfalls.md.

Every client is read-only, cached on disk by accession number, and returns the
provider's payload untouched. Turning a payload into FinancialFact rows is
data/normalize/'s job, so a change to a provider's shape never reaches the rest
of the system.
"""
