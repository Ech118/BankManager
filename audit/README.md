# audit

**Owner: P2 (Calc, Audit & Eval).** Only the owner edits this directory (plan.txt 15.4).

Auditor: numbers trace to sources, evidence quotes appear verbatim in source text, disclaimer present, consistency. Public interface: api.py.

## Layout
- `checks.py` - the four checks: numbers-trace, evidence-quote verification, disclaimer, consistency (delegates to `calc.consistency`).
- `api.py` - `run_audit`, the frozen public interface.
- `tests/` - includes the plan's explicit bar: catches an injected fake number and a fabricated quote.
