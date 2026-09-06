#!/usr/bin/env bash
set -euo pipefail

edge_id="${1:?usage: rotate-certificates.sh EDGE_ID}"
api_url="${CLOUDCTL_API_URL:?CLOUDCTL_API_URL is required}"
operator_token="${CLOUDCTL_OPERATOR_TOKEN:?CLOUDCTL_OPERATOR_TOKEN is required}"

curl --fail --silent --show-error \
  --request POST \
  --header "Authorization: Bearer $operator_token" \
  --header "Content-Type: application/json" \
  --data "{\"edgeId\":\"$edge_id\"}" \
  "$api_url/api/v1/edges/$edge_id/certificate-rotations" >/dev/null

echo "Rotation requested. The new certificate is delivered only over the authenticated Edge channel."

