"""P2: the forward paper-trading log. Specified by docs/roadmap.md Step 6.

An append-only record of every prediction the system makes, dated and hashed, so
it can be graded when the horizon arrives.

WHY THIS IS THE MOST TRUSTWORTHY EVALUATION WE HAVE. A backtest can be
contaminated by the model's own memory of what happened. A prediction recorded
today about a period that has not happened yet cannot be. It is slow - the
one-year results take a year - but it is the only evaluation whose validity does
not depend on an argument about training data.

Append-only, and never edited after the fact. A prediction log that can be
revised is not evidence.
"""
