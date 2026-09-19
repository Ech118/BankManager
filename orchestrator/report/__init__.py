"""P3: the report generator. Renders a Verdict from a ResearchState.

Specified by docs/research-state.md and docs/adr/0004.

DETERMINISTIC AND TEMPLATED. No LLM runs here. The same ResearchState always
renders the same report, which means every sentence a reader sees traces back to
a Claim, and every Claim has been through the verification gate.

This is what stops free-form agent prose reaching the reader unchecked: the
agents write Claims, and only Claims get rendered.
"""
