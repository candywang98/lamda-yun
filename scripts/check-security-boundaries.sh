#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

failure=0

while IFS= read -r match; do
  [[ -z "$match" ]] && continue
  echo "LAMDA import outside packages/lamda-driver: $match" >&2
  failure=1
done < <(
  grep -RInE '(^|[[:space:]])(from[[:space:]]+lamda|import[[:space:]]+lamda)' \
    --include='*.py' . \
    --exclude-dir=.venv \
    --exclude-dir=node_modules \
    --exclude-dir=dist \
    --exclude-dir=.mypy_cache \
    --exclude-dir=lamda-driver || true
)

while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  if grep -Eq '(^|[^0-9])65000([^0-9]|$)' "$file"; then
    echo "Device port 65000 appears in deployable configuration: $file" >&2
    failure=1
  fi
done < <(find infra services apps -type f \( -name '*.yml' -o -name '*.yaml' -o -name '*.tf' -o -name 'Caddyfile' \) 2>/dev/null)

if grep -RInE \
  --include='*.py' --include='*.ts' --include='*.vue' --include='*.kt' \
  --include='*.yml' --include='*.yaml' --include='*.json' \
  '(-----BEGIN (RSA |EC )?PRIVATE KEY-----|AKIA[0-9A-Z]{16})' . \
  --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=dist; then
  echo "A private key or access key pattern was found." >&2
  failure=1
fi

if (( failure != 0 )); then
  exit 1
fi

echo "Security boundary checks passed."
