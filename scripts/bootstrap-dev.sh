#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
fi

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

if ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm is required; install it with Corepack before running this script" >&2
  exit 1
fi
pnpm install

echo "CloudCtl development dependencies are ready."

