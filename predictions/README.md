# predictions

**Owner: P2 (Calc, Audit & Eval).** Only the owner edits this directory (plan.txt 15.4).

Append-only forward paper-trading log: <date>_<ticker>_<inputhash>.json per run.

## Layout
- `logger.py` - `log_prediction` (idempotent for identical inputs, never overwrites an existing file), `list_predictions`, `grade_prediction` (appends a *new* `.graded.json` file; never mutates the original).
- `log/` - generated output, gitignored (nested `.gitignore`, plan.txt 15.5).
