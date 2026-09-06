#!/usr/bin/env bash
set -euo pipefail

destination="${1:?usage: backup.sh DESTINATION_DIRECTORY}"
umask 077
mkdir -p "$destination"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"

: "${PGHOST:=127.0.0.1}"
: "${PGPORT:=5432}"
: "${PGDATABASE:=cloudctl}"
: "${PGUSER:=cloudctl}"

pg_dump --format=custom --no-owner --file "$destination/postgres-$timestamp.dump"
sha256sum "$destination/postgres-$timestamp.dump" > "$destination/postgres-$timestamp.dump.sha256"

printf '{"createdAt":"%s","database":"%s","containsSecrets":false}\n' \
  "$timestamp" "$PGDATABASE" > "$destination/manifest-$timestamp.json"

echo "Backup created in $destination. Object storage must be backed up with its versioned replication policy."

