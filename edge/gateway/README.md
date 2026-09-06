# CloudCtl Edge Gateway

The gateway is an outbound-only Edge runtime. It holds the device-side lease/fencing boundary,
serves the certificate-pinned Companion API over HTTPS, and connects to Edge Hub with mTLS.

Run a network-free startup check:

```bash
PYTHONPATH=packages/edge-protocol/src:packages/lamda-driver/src:packages/automation-sdk/src:edge/gateway/src \
  .venv/bin/python -m cloudctl_edge --check
```

Production startup requires these environment variables:

- `CLOUDCTL_EDGE_ID`
- `CLOUDCTL_HUB_ENDPOINT` (an `https://` Edge Hub endpoint; device port 65000 is rejected)
- `CLOUDCTL_STATE_DIR`
- `CLOUDCTL_ARTIFACT_STAGING_ROOT`
- `CLOUDCTL_EDGE_CREDENTIALS_DIR` containing `edge.crt`, `edge.key`, and `ca.crt`
- `CLOUDCTL_COMPANION_TLS_CERTIFICATE`
- `CLOUDCTL_COMPANION_TLS_PRIVATE_KEY`
- `CLOUDCTL_COMPANION_BIND_HOST`
- `CLOUDCTL_COMPANION_BIND_PORT` (defaults to 8443)
- `CLOUDCTL_DEVICE_PROFILES_PATH`
- `CLOUDCTL_COMPANION_ENROLLMENT_PATH`

Device profile configuration:

```json
{
  "devices": [
    {
      "deviceId": "device-a",
      "host": "10.0.0.20",
      "certificatePath": "/etc/cloudctl/devices/device-a.pem",
      "allowedPackages": ["com.company.approved"]
    }
  ]
}
```

One-time Companion enrollment configuration:

```json
{
  "enrollments": [
    {
      "code": "ROTATE-THIS-ONE-TIME-CODE",
      "deviceId": "device-a",
      "tenantName": "Authorized tenant",
      "siteName": "Authorized site"
    }
  ]
}
```

Enrollment codes and bearer tokens are stored only as SHA-256 digests. A consumed enrollment code
is not reactivated when the gateway restarts. Real LAMDA operations remain `blocked_hardware` until
the configured device, service certificate, lease, and fencing token are all available.

