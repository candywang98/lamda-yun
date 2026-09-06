#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit_source="$repo_root/services/edge-hub/deploy/cloudctl-edge-hub.service"
unit_target="/etc/systemd/system/cloudctl-edge-hub.service"
tls_root="/etc/cloudctl-edge-hub/tls"

if [[ $EUID -ne 0 ]]; then
  echo "install-edge-hub-systemd.sh must run as root" >&2
  exit 1
fi

if [[ ! -f "$unit_source" ]]; then
  echo "Edge Hub systemd unit is missing: $unit_source" >&2
  exit 1
fi

if ! getent group cloudctl-edge-hub >/dev/null; then
  groupadd --system cloudctl-edge-hub
fi
if ! id cloudctl-edge-hub >/dev/null 2>&1; then
  useradd --system --gid cloudctl-edge-hub --home-dir /nonexistent --shell /usr/sbin/nologin cloudctl-edge-hub
fi

install -d -m 0750 -o root -g cloudctl-edge-hub /etc/cloudctl-edge-hub
install -d -m 0750 -o root -g cloudctl-edge-hub "$tls_root"
install -m 0644 -o root -g root "$unit_source" "$unit_target"
systemctl daemon-reload

for required_file in server.crt server.key client-ca.crt; do
  if [[ ! -s "$tls_root/$required_file" ]]; then
    echo "Required non-empty TLS file not installed: $tls_root/$required_file" >&2
    missing_tls=1
  fi
done

if [[ ${missing_tls:-0} -ne 0 ]]; then
  echo "Unit installed but not enabled or started. Provision reviewed TLS material, then rerun." >&2
  exit 2
fi

chown root:cloudctl-edge-hub "$tls_root/server.crt" "$tls_root/server.key" "$tls_root/client-ca.crt"
chmod 0640 "$tls_root/server.crt" "$tls_root/client-ca.crt"
chmod 0640 "$tls_root/server.key"
systemctl enable cloudctl-edge-hub.service

echo "Installed and enabled cloudctl-edge-hub.service; start it explicitly after validation."
echo "This installer does not generate a CA and does not start or modify GenericAgent."
