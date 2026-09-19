# Contributing

Three people build this repo simultaneously. These rules exist so that work
merges cleanly *and* the pieces still fit when it does.

---

## Branch naming

| Prefix | For |
|---|---|
| `p1/` | P1 work — e.g. `p1/edgar-client` |
| `p2/` | P2 work — e.g. `p2/weight-clamping` |
| `p3/` | P3 work — e.g. `p3/coordinator` |
| `contracts/` | contract changes — e.g. `contracts/add-segment-facts` |

The long-lived partition branches are `p1-data`, `p2-calc` and `p3-agents`.
Feature branches use the prefixes above and merge into `main`.

Never force-push `main`. Never rewrite shared history.

---

## Before every push

```bash
make lint
make test-contracts
make check-ownership P=p1|p2|p3
```

`check-ownership` fails if you touched a path outside your partition. It is not
advisory — a PR that fails it will not be reviewed.

Stage explicit paths. Never `git add -A` or `git add .`: it is how `.env` files
and stray caches get committed.

Commit messages carry a partition prefix: `[p1]`, `[p2]`, `[p3]`, `[step0]`.

---

## Pull requests

Every PR must:

1. Pass `make lint` and `make test-contracts` in CI.
2. Touch only your partition's paths (or be a contract-change PR).
3. **Update `docs/pN/STATUS.md`** if it changes what works. A PR that moves a
   capability from mock to real and leaves STATUS stale is incomplete — STATUS
   is how the other two partitions know what they can rely on.
4. Fill in the template, including the contract-change checkbox.

Keep PRs inside one partition. A PR spanning two is a sign something should have
been a request instead.

---

## Contract change process

`schema/` is shared. Changing it changes everyone's world, so it has its own
process.

### What counts as a contract change

- anything in `schema/contracts/` or `schema/*.json`
- any `api.py` signature (`data/`, `calc/`, `audit/`, `orchestrator/`)
- any Protocol in `schema/contracts/interfaces.py`
- any MCP tool request or response shape

`tests/contracts/test_signatures.py` and `test_schema_export.py` will fail if
you change one of these without following the process, which is the point.

### Additive vs breaking

**Additive** — a new optional field, a new enum member, a new tool. Old readers
keep working; every artifact model sets `extra="allow"`.

**Breaking** — a rename, a removal, a retype, a changed signature, a new
required field.

### The process

1. **Propose.** Add `docs/requests/YYYY-MM-DD-pX-to-pY-<slug>.md` stating what
   you need, why, the exact field or function, and the urgency. Never edit an
   existing request file — a new file can never conflict.
2. **Get approval.** Additive: the producing partition's owner plus the
   coordinator. Breaking: **all three partitions**, written into the request
   file.
3. **Apply.** The coordinator (P3 by default) makes the change in ONE commit on
   a `contracts/` branch:
   - edit `schema/contracts/`
   - `make gen-schema`
   - `make gen-mock`
   - bump `SCHEMA_VERSION` (and `STATE_VERSION` if the state shape moved)
   - add a `schema/CHANGELOG.md` entry
   - update `tests/contracts/` if signatures moved
4. **Verify.** `make lint && make test-contracts` must pass before merge.
5. **Pull.** Everyone rebases on `main`.

### While you wait

Keep working against the mock. That is what mock mode is for — a blocked
partition is a planning failure, not an inevitability.

---

## Cross-partition requests

Never edit another partition's files, including to fix an obvious bug.

```
docs/requests/YYYY-MM-DD-pX-to-pY-<slug>.md
```

Say what you need, why, and — for a bug — the minimal repro. The owner replies
by ADDING a sibling `-response.md` and does the work in their own directory.

New files only. That is what keeps merges conflict-free.

---

## Tests

| Suite | Owner | Runs |
|---|---|---|
| `tests/contracts/` | shared, frozen | every commit, every PR |
| `data/tests/` | P1 | P1's commits |
| `calc/tests/`, `audit/tests/` | P2 | P2's commits |
| `agents/tests/`, `orchestrator/tests/` | P3 | P3's commits |
| `tests/e2e/` | P3 | checkpoints |

**The producer of an artifact is responsible for making it validate.** If a
contract test fails on *your* output, fix it. If it fails on another
partition's, file a request — do not fix their code.

Step 0 ships placeholder tests marked `skip` with a reason. The skip list is the
shortest readable statement of what each partition still owes.

---

## Secrets

Real keys live only in your local, gitignored `.env`. `make setup` installs a
pre-commit scan that blocks commits containing key-shaped strings.

Never paste a key into code, a fixture, a doc, a commit message or a chat.

---

## Working with Claude

Each person runs their own Claude instance on one partition. [CLAUDE.md](CLAUDE.md)
is loaded automatically; `docs/pN/CLAUDE.md` holds the partition rules, and each
owned directory carries a short pointer `CLAUDE.md`.

Tell your instance which partition it is at the start of every session. It is
instructed to ask rather than guess.
