#!/usr/bin/env bash
set -euo pipefail

install_root="${CLOUDCTL_EDGE_ROOT:-/opt/cloudctl-edge}"
config_root="${CLOUDCTL_EDGE_CONFIG:-/etc/cloudctl-edge}"

if [[ $EUID -ne 0 ]]; then
  echo "edge-install.sh must run as root on the authorized Edge host" >&2
  exit 1
fi

install -d -m 0750 -o root -g root "$install_root"
install -d -m 0700 -o root -g root "$config_root"

if [[ -z "${CLOUDCTL_ENROLLMENT_TOKEN:-}" ]]; then
  echo "CLOUDCTL_ENROLLMENT_TOKEN is required and is consumed by the enrollment client" >&2
  exit 1
fi

echo "Directories created. Run the packaged enrollment client; this script never writes tokens to disk."

