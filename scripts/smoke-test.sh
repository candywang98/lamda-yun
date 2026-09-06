#!/usr/bin/env bash
set -euo pipefail

api_url="${CLOUDCTL_API_URL:-http://127.0.0.1:8000}"
web_url="${CLOUDCTL_WEB_URL:-http://127.0.0.1:5173}"

curl --fail --silent --show-error "$api_url/health/live" >/dev/null
curl --fail --silent --show-error "$api_url/health/ready" >/dev/null
curl --fail --silent --show-error "$api_url/openapi.json" >/dev/null
curl --fail --silent --show-error "$web_url" >/dev/null

echo "Control-plane smoke tests passed. Device checks require an explicit authorized profile."

