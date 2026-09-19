#!/usr/bin/env bash
# FROZEN (Step 0). Blocks commits that contain secrets.
# usage: scripts/secret_scan.sh          scan STAGED changes (used by the pre-commit hook)
#        scripts/secret_scan.sh --all    scan every tracked file
set -uo pipefail

PATTERNS=(
  'sk-ant-[A-Za-z0-9_-]{20,}'
  'sk-[A-Za-z0-9]{32,}'
  'ghp_[A-Za-z0-9]{30,}'
  'github_pat_[A-Za-z0-9_]{30,}'
  'AKIA[0-9A-Z]{16}'
  '-----BEGIN ((RSA|EC|OPENSSH) )?PRIVATE KEY-----'
  '(ANTHROPIC|FMP|FRED|TAVILY)_API_KEY[[:space:]]*[=:][[:space:]]*["'"'"']?[A-Za-z0-9_-]{16,}'
)

if [ "${1:-}" = "--all" ]; then
  FILES="$(git ls-files)"
  CONTENT_CMD() { git grep -nIE -e "$1" -- . ':!scripts/secret_scan.sh' 2>/dev/null; }
else
  FILES="$(git diff --cached --name-only --diff-filter=ACM)"
  CONTENT_CMD() { git diff --cached -U0 --no-color -- . ':!scripts/secret_scan.sh' | grep -E '^\+' | grep -vE '^\+\+\+' | grep -E -e "$1"; }
fi

bad=0
for f in $FILES; do
  case "$(basename "$f")" in
    .env|.env.*|*.pem|id_rsa|id_ed25519)
      if [ "$(basename "$f")" != ".env.example" ]; then echo "SECRET SCAN: refusing to commit secret-like file: $f"; bad=1; fi ;;
  esac
done
for pat in "${PATTERNS[@]}"; do
  if hits="$(CONTENT_CMD "$pat")" && [ -n "$hits" ]; then
    echo "SECRET SCAN: pattern /$pat/ matched:"
    echo "$hits" | sed 's/\(.\{160\}\).*/\1.../'
    bad=1
  fi
done
if [ "$bad" -ne 0 ]; then
  echo "Commit blocked. Remove the secret (keep real keys in your local, gitignored .env)."
  exit 1
fi
echo "secret scan clean"
