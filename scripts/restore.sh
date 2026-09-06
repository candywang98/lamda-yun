#!/usr/bin/env bash
set -euo pipefail

archive="${1:?usage: restore.sh DATABASE_DUMP}"
checksum="$archive.sha256"

if [[ ! -f "$checksum" ]]; then
  echo "Missing checksum file: $checksum" >&2
  exit 1
fi

sha256sum --check "$checksum"

: "${PGHOST:=127.0.0.1}"
: "${PGPORT:=5432}"
: "${PGDATABASE:=cloudctl}"
: "${PGUSER:=cloudctl}"

if [[ "${CLOUDCTL_RESTORE_CONFIRMED:-}" != "yes" ]]; then
  echo "Set CLOUDCTL_RESTORE_CONFIRMED=yes after completing the restore change review." >&2
  exit 1
fi

pg_restore --exit-on-error --clean --if-exists --no-owner --dbname "$PGDATABASE" "$archive"
echo "Database restore completed; run migrations and smoke tests before serving traffic."

