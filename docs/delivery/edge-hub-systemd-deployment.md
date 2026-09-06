# Edge Hub systemd deployment

This asset runs only the CloudCtl Edge Hub on `0.0.0.0:7443`. It does not install,
stop, restart, or alter GenericAgent. The service's `ProtectHome=true` sandbox also
prevents it from reading `/home/ubuntu/GenericAgent`.

## Prerequisites

- Install the CloudCtl wheel and its pinned dependencies into
  `/opt/cloudctl-edge-hub/venv`.
- Point `/opt/cloudctl-edge-hub/current` at the reviewed release directory.
- Provision an already-reviewed server certificate, matching private key, and the
  client CA used to issue Edge Gateway certificates. Production CA generation is
  deliberately outside this repository and installer.

Install the three non-empty TLS files with these exact paths:

```text
/etc/cloudctl-edge-hub/tls/server.crt
/etc/cloudctl-edge-hub/tls/server.key
/etc/cloudctl-edge-hub/tls/client-ca.crt
```

Then run:

```bash
sudo ./scripts/install-edge-hub-systemd.sh
sudo systemctl start cloudctl-edge-hub.service
sudo systemctl status cloudctl-edge-hub.service
sudo journalctl -u cloudctl-edge-hub.service -n 50 --no-pager
```

Readiness is reported by the structured startup log
`edge_hub_ready bind=0.0.0.0:7443 mtls=required`. A TCP listener alone does not
prove readiness: unauthenticated clients are rejected by gRPC because the server
credentials are always created with `require_client_auth=True`.

The process handles `SIGTERM` and `SIGINT`, stops accepting work, and gives active
RPCs up to 20 seconds to finish. The systemd unit allows 30 seconds before forced
termination.

Port `65000` is reserved for the device-local service and is rejected by the
runtime configuration. It must never be exposed by this cloud service.
