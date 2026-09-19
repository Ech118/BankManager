# P1 -> coordinator: `make test` fails to collect, on a clean main

**Urgency:** low for the demo (`make test-contracts` is unaffected), annoying for
anyone who runs the documented `make test`.

## What happens

On a clean `origin/main`, with no partition changes:

```
$ make test
ERROR calc/tests/test_placeholders.py
ERROR audit/tests/test_placeholders.py
ERROR agents/tests/test_placeholders.py
ERROR orchestrator/tests/test_placeholders.py
ERROR tests/e2e/test_placeholders.py
!!!!!!!!!!!!!!!!!!! Interrupted: 5 errors during collection !!!!!!!!!!!!!!!!!!!!
```

The underlying error:

```
import file mismatch:
imported module 'test_placeholders' has this __file__ attribute:
  data/tests/test_placeholders.py
which is not the same as the test file we want to collect:
  calc/tests/test_placeholders.py
```

Each test directory holds a `test_placeholders.py` and none of them is a package,
so pytest derives the module name `test_placeholders` six times over and the
second one collides with the first.

Running any one directory on its own is fine, which is why this has not bitten
anyone yet:

```
$ python -m pytest calc/tests -q
14 skipped
```

## Fix

One empty `__init__.py` per test directory:

```
calc/tests/__init__.py
audit/tests/__init__.py
agents/tests/__init__.py
orchestrator/tests/__init__.py
tests/e2e/__init__.py
```

I have added `data/tests/__init__.py` in my own partition. The other five are
outside P1, so I have not touched them.

(`--import-mode=importlib` in a pytest config would fix it centrally instead, if
you would rather not add the files. Either works; the Makefile and any pytest
config are yours.)

## Why it is worth fixing

`make test` is step 2 of the documented pre-commit routine in every partition's
CLAUDE.md. Right now it fails for reasons unrelated to the change being tested,
which trains people to skip it.

— P1
