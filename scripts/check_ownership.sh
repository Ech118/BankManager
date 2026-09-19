#!/usr/bin/env bash
# FROZEN (Step 0). Fails if your changes touch paths outside your partition.
# usage: scripts/check_ownership.sh p1|p2|p3|contracts|coordinator|step0
# Checks BOTH committed changes (vs $BASE, default origin/main) and staged changes.
set -euo pipefail

ROLE="${1:-}"
BASE="${BASE:-origin/main}"

case "$ROLE" in
  p1) ALLOWED="data/ mcp_server/ fixtures/real/ docs/p1/" ;;
  p2) ALLOWED="calc/ audit/ backtest/ predictions/ docs/p2/" ;;
  p3) ALLOWED="agents/ prompts/ orchestrator/ web/ tests/e2e/ docs/p3/" ;;
  # A contract-change PR touches the shared contract surface. It needs written
  # approval from all three partitions first (CONTRIBUTING.md).
  contracts) ALLOWED="schema/ fixtures/mock/ tests/contracts/ scripts/gen_schema.py scripts/gen_mock_fixtures.py data/api.py calc/api.py audit/api.py orchestrator/api.py" ;;
  coordinator) ALLOWED="schema/ fixtures/mock/ tests/contracts/ scripts/ .gitignore .env.example ruff.toml README.md CLAUDE.md ARCHITECTURE.md CONTRIBUTING.md Makefile docs/ .github/ archive/" ;;
  step0) echo "role step0: everything allowed (initial skeleton commit only)"; exit 0 ;;
  *) echo "usage: $0 p1|p2|p3|contracts|coordinator|step0" >&2; exit 2 ;;
esac

if ! git rev-parse --verify --quiet "$BASE" >/dev/null; then
  echo "warning: base '$BASE' not found; checking staged changes only" >&2
  CHANGES="$(git diff --name-status --no-renames --cached)"
else
  CHANGES="$( { git diff --name-status --no-renames "$BASE"...HEAD; git diff --name-status --no-renames --cached; } | sort -u )"
fi

bad=0
while IFS=$'\t' read -r status path; do
  [ -z "${path:-}" ] && continue
  ok=0
  for prefix in $ALLOWED; do
    case "$path" in "$prefix"*) ok=1 ;; esac
  done
  # docs/requests/: anyone may ADD new files, nobody may modify/delete existing ones.
  # New files cannot conflict, which is what keeps cross-partition asks merge-safe.
  case "$path" in
    docs/requests/*) if [ "$status" = "A" ]; then ok=1; else ok=0; fi ;;
  esac
  if [ "$ok" -eq 0 ]; then
    echo "OWNERSHIP VIOLATION ($ROLE): $status $path"
    bad=1
  fi
done <<< "$CHANGES"

if [ "$bad" -ne 0 ]; then
  echo
  echo "You may only change: $ALLOWED"
  echo "(plus NEW files in docs/requests/)"
  echo
  echo "Need a change elsewhere? File a request:"
  echo "  docs/requests/YYYY-MM-DD-pX-to-pY-<slug>.md"
  echo "Changing schema/ or an api.py signature is a CONTRACT-CHANGE PR and needs"
  echo "approval from all three partitions. See CONTRIBUTING.md."
  exit 1
fi
echo "ownership OK ($ROLE)"
