# LAMDA sidecar

CloudCtl runs LAMDA `10.8` outside the main Edge Gateway interpreter. The main project remains on
`protobuf==7.36.0`; the sidecar uses Python `3.12`, LAMDA `10.8`, and its compatible
`protobuf==6.33.6`. The two dependency graphs communicate only through a versioned, allowlisted
JSON-lines protocol over the child process standard streams. No TCP listener is created.

## Runtime preparation

Create the sidecar environment on the Edge data volume, not on the operating-system volume:

```bash
export UV_CACHE_DIR=/data/cloudctl/uv-cache
export UV_PYTHON_INSTALL_DIR=/data/cloudctl/python
uv python install 3.12
uv venv --python 3.12 /data/cloudctl/lamda-python312
uv pip install --python /data/cloudctl/lamda-python312/bin/python 'lamda==10.8'
```

Configure the absolute interpreter path:

```bash
export CLOUDCTL_LAMDA_SIDECAR_PYTHON=/data/cloudctl/lamda-python312/bin/python
```

The verified local Windows/WSL development installation is
`/mnt/d/android-tools/lamda-wsl-python312/bin/python`. Caches, downloads, build products, and the
runtime itself are on drive D.

## Startup gate

Gateway composition starts the sidecar only for a local handshake and rejects startup unless all
of these are true:

- the configured interpreter is an existing absolute path;
- the sidecar protocol major is `1`;
- Python is `3.12.x`;
- LAMDA is exactly `10.8`;
- the device certificate and content-addressed artifact cache are available.

The sidecar process receives the device host, approved port, certificate path, and the fixed Edge
artifact-object root through stdin, never through command-line arguments. It accepts only the
driver operation allowlist. It does not expose shell, ADB, SSH, arbitrary method calls, or a
network listener.

## Artifact boundary

Media and APK operations send only a SHA256 digest, expected size, and approved destination or APK
session metadata. The sidecar derives the local path as `<objects>/<sha256-prefix>/<sha256>`,
rejects symlinks and path escape, then rechecks size and SHA256 immediately before device I/O.
The cloud plane and browser never receive the cache path or device certificate.

## Lease and failure behavior

`LamdaSession` verifies the database-backed lease ID and fencing token before sidecar startup,
before every driver operation, and before every LAMDA lock refresh. A stale fence stops further
device I/O. The device API lock remains a 60-second lease refreshed every 20 seconds; process loss
therefore does not create an indefinite lock.

Remote SDK failures are reduced to the existing `DriverErrorCode`, redacted detail, retryability,
and reconciliation flag. SDK tracebacks, endpoint detail, certificate contents, input text, and
artifact bytes are not returned to the Gateway log stream.

## Verification

```bash
.venv/bin/python -m pytest -q \
  tests/edge_lamda_sidecar_test.py \
  tests/edge_lamda_driver_test.py \
  tests/edge_runtime_test.py \
  tests/edge_executor_test.py
.venv/bin/python -m ruff check packages/lamda-driver edge/gateway
.venv/bin/python -m mypy packages/lamda-driver/src/cloudctl_lamda_driver edge/gateway/src/cloudctl_edge
scripts/check-security-boundaries.sh
```

Real device acceptance remains blocked until an authorized LAMDA Android service, matching device
certificate, and port `65000` are available. Installing the Python sidecar alone does not satisfy
hardware acceptance.
