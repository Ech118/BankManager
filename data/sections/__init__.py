"""P1 filing-section parsing: split filings by STRUCTURE, not by token window.

Specified by docs/adr/0006 and docs/data-model.md "Filing sections".

A 10-K already has a structure the SEC mandates: Items, and numbered notes to
the financial statements. Splitting on that structure gives sections an agent
can be pointed at by name ("give me the debt note"), and gives the verifier a
stable anchor for quote checking. Chunking the same document into overlapping
windows would throw that structure away and then try to recover it statistically.
"""
