#!/usr/bin/env bash
set -euo pipefail

artifact="${1:?usage: edge-upgrade.sh SIGNED_ARTIFACT}"
checksum_file="$artifact.sha256"

test -f "$checksum_file"
sha256sum --check "$checksum_file"

if [[ "${CLOUDCTL_EDGE_DRAINED:-}" != "yes" ]]; then
  echo "Drain the Edge and set CLOUDCTL_EDGE_DRAINED=yes before upgrading." >&2
  exit 1
fi

echo "Artifact verified. Installation is delegated to the platform package manager."

