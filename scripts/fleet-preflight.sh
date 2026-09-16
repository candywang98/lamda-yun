#!/usr/bin/env bash
# fleet-preflight.sh — fleet deploy identity, backup/restore-verify and auth probes (D10).
#
# Subcommands:
#   backup DEST_DIR [--objects-dir DIR]
#       pg_dump (custom format) + sha256 sidecar + object-store inventory manifest.
#       Connection uses standard libpq env (PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD);
#       defaults: 127.0.0.1:5432, db/user "cloudctl". For the Seoul host see
#       docs/runbooks/fleet-deploy.md (only inside an authorized change window).
#
#   restore-verify DUMP [--keep]
#       Restores DUMP into an isolated temp database (createdb cloudctl_pverify_<ts>),
#       compares table sets, per-table row counts and order-independent row digests
#       against the live source database, then drops the temp database.
#       Exit 0 = tasks/intents/object digests all consistent; exit 1 = any mismatch.
#
#   probe-auth BASE_URL [--path /api/v1/session] [--mode strict|dev-bypass]
#                [--require-tls] [--insecure]
#       Anonymous / forged-bearer / forged-role-header / cross-tenant probes.
#       strict (default): every forged identity MUST be rejected (401/403).
#       dev-bypass: staging posture — dev identity headers are expected to
#       authenticate (with a loud warning); anonymous/forged-bearer must still 401.
#
#   version BASE_URL [--compose-dir DIR] [--require-build]
#       Health endpoint census + build identity (BUILD_SHA) discovery.
#
# Dependencies: bash, curl, psql/pg_dump/pg_restore/createdb/dropdb (backup &
# restore-verify only), sha256sum or shasum. No python, no jq.
#
# Exit codes: 0 pass, 1 failure, 2 usage error.

set -euo pipefail

PROGRAM_NAME="fleet-preflight"
FAILURES=0

log() { printf '[%s] %s\n' "$PROGRAM_NAME" "$*"; }
warn() { printf '[%s] WARN: %s\n' "$PROGRAM_NAME" "$*" >&2; }
fail() { printf '[%s] FAIL: %s\n' "$PROGRAM_NAME" "$*" >&2; FAILURES=$((FAILURES + 1)); }
die() { printf '[%s] ERROR: %s\n' "$PROGRAM_NAME" "$*" >&2; exit 1; }

usage() {
  sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1 (see subcommand requirements in header)"
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

git_sha() {
  if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git rev-parse HEAD 2>/dev/null || printf ''
  else
    printf ''
  fi
}

# ---------------------------------------------------------------------------
# backup
# ---------------------------------------------------------------------------
cmd_backup() {
  [ $# -ge 1 ] || die "usage: $0 backup DEST_DIR [--objects-dir DIR]"
  local dest_dir="$1"
  shift
  local objects_dir=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --objects-dir)
        [ $# -ge 2 ] || die "--objects-dir requires a value"
        objects_dir="$2"
        shift 2
        ;;
      *) die "unknown option: $1" ;;
    esac
  done

  require_cmd pg_dump

  : "${PGHOST:=127.0.0.1}"
  : "${PGPORT:=5432}"
  : "${PGDATABASE:=cloudctl}"
  : "${PGUSER:=cloudctl}"

  umask 077
  mkdir -p "$dest_dir"
  local timestamp
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  local dump="$dest_dir/postgres-$timestamp.dump"

  log "pg_dump ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE} -> $dump"
  pg_dump --format=custom --no-owner --file "$dump" || die "pg_dump failed"
  local dump_sha
  dump_sha="$(sha256_file "$dump")"
  printf '%s  %s\n' "$dump_sha" "$(basename "$dump")" > "$dump.sha256"

  local objects_count=0 legal_hold_count=0
  local objects_manifest="$dest_dir/objects-$timestamp.tsv"
  if [ -n "$objects_dir" ]; then
    [ -d "$objects_dir" ] || die "--objects-dir is not a directory: $objects_dir"
    printf 'sha256\tsize\tlegal_hold\trelpath\n' > "$objects_manifest"
    local rel size sha flag
    while IFS= read -r f; do
      rel="${f#"$objects_dir"/}"
      size="$(wc -c < "$f" | tr -d ' ')"
      sha="$(sha256_file "$f")"
      case "$rel" in
        legal-hold/*|*/legal-hold/*) flag="1"; legal_hold_count=$((legal_hold_count + 1)) ;;
        *) flag="0" ;;
      esac
      printf '%s\t%s\t%s\t%s\n' "$sha" "$size" "$flag" "$rel" >> "$objects_manifest"
      objects_count=$((objects_count + 1))
    done < <(find "$objects_dir" -type f | LC_ALL=C sort)
    log "object inventory: $objects_count files ($legal_hold_count under legal-hold/) -> $objects_manifest"
  else
    warn "no --objects-dir given; object store not inventoried (S3 buckets need their inventory export or 'mc mirror --dry-run' listing)"
    rm -f "$objects_manifest"
  fi

  local manifest="$dest_dir/manifest-$timestamp.json"
  {
    printf '{"createdAt":"%s","gitSha":"%s","database":"%s","pgHost":"%s","pgPort":"%s"' \
      "$timestamp" "$(git_sha)" "$PGDATABASE" "$PGHOST" "$PGPORT"
    printf ',"dump":"%s","dumpSha256":"%s"' "$(basename "$dump")" "$dump_sha"
    printf ',"objectsDir":"%s","objectsCount":%s,"legalHoldCount":%s' \
      "${objects_dir:-}" "$objects_count" "$legal_hold_count"
    printf ',"containsSecrets":false}\n'
  } > "$manifest"
  log "backup complete: $dump (+.sha256) and $manifest"

  if [ "$FAILURES" -gt 0 ]; then exit 1; fi
  exit 0
}

# ---------------------------------------------------------------------------
# restore-verify
# ---------------------------------------------------------------------------
table_list() { # table_list <psql target prefix args...> — caller passes db
  psql -X -qAt -d "$1" -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
}

table_count() { # table_count DB TABLE
  psql -X -qAt -d "$1" -c "SELECT count(*) FROM \"$2\""
}

table_digest() { # table_digest DB TABLE — order-independent full-row digest
  psql -X -qAt -d "$1" -c "SELECT md5(coalesce(string_agg(md5(t::text), '' ORDER BY md5(t::text)), '')) FROM \"$2\" AS t"
}

cmd_restore_verify() {
  [ $# -ge 1 ] || die "usage: $0 restore-verify DUMP [--keep]"
  local dump="$1"
  shift
  local keep=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --keep) keep=1; shift ;;
      *) die "unknown option: $1" ;;
    esac
  done

  [ -f "$dump" ] || die "dump file not found: $dump"
  require_cmd pg_restore
  require_cmd psql
  require_cmd createdb
  require_cmd dropdb

  : "${PGHOST:=127.0.0.1}"
  : "${PGPORT:=5432}"
  : "${PGDATABASE:=cloudctl}"
  : "${PGUSER:=cloudctl}"

  if [ -f "$dump.sha256" ]; then
    local expected actual
    expected="$(awk '{print $1}' "$dump.sha256")"
    actual="$(sha256_file "$dump")"
    if [ "$expected" = "$actual" ]; then
      log "dump checksum OK ($actual)"
    else
      fail "dump checksum mismatch: expected $expected got $actual"
      exit 1
    fi
  else
    warn "no $dump.sha256 sidecar; skipping dump integrity check"
  fi

  local temp_db="cloudctl_pverify_$(date -u +%Y%m%d%H%M%S)"
  createdb "$temp_db" || die "createdb $temp_db failed"
  cleanup() {
    if [ "$keep" = "1" ]; then
      log "keeping temp database $temp_db for inspection"
    else
      dropdb "$temp_db" >/dev/null 2>&1 || warn "failed to drop temp database $temp_db (drop it manually)"
    fi
  }
  trap cleanup EXIT

  log "pg_restore -> isolated temp database $temp_db"
  pg_restore --exit-on-error --no-owner --dbname "$temp_db" "$dump" \
    || { fail "pg_restore reported errors"; exit 1; }

  local src_tables rst_tables
  src_tables="$(table_list "$PGDATABASE")"
  rst_tables="$(table_list "$temp_db")"
  if [ "$src_tables" != "$rst_tables" ]; then
    fail "table sets differ between $PGDATABASE and restored $temp_db"
    diff <(printf '%s\n' "$src_tables") <(printf '%s\n' "$rst_tables") >&2 || true
    exit 1
  fi

  local tables_changed=0
  local table c_src c_rst d_src d_rst
  # business highlights called out by the D10 acceptance: tasks, intents, object summaries
  local highlights="mobile_task commit_intent media_asset media_object fleet_device_session alembic_version"
  for table in $src_tables; do
    c_src="$(table_count "$PGDATABASE" "$table")"
    c_rst="$(table_count "$temp_db" "$table")"
    d_src="$(table_digest "$PGDATABASE" "$table")"
    d_rst="$(table_digest "$temp_db" "$table")"
    if [ "$c_src" = "$c_rst" ] && [ "$d_src" = "$d_rst" ]; then
      log "table OK  $table rows=$c_src digest=$d_src"
    else
      fail "table MISMATCH $table source(rows=$c_src digest=$d_src) restored(rows=$c_rst digest=$d_rst)"
      tables_changed=$((tables_changed + 1))
    fi
  done

  local h found
  for h in $highlights; do
    case "
$src_tables" in
      *"
$h"*) log "highlight present: $h" ;;
      *) warn "highlight table not present (fresh/simplified dataset): $h" ;;
    esac
  done

  if [ "$tables_changed" -gt 0 ]; then
    log "restore-verify FAILED: $tables_changed table(s) inconsistent"
    exit 1
  fi
  log "restore-verify PASSED: all $(printf '%s\n' "$src_tables" | grep -c .) public table(s) identical (rows+digest)"
  exit 0
}

# ---------------------------------------------------------------------------
# probe-auth
# ---------------------------------------------------------------------------
http_status() { # http_status URL [curl args...] -> code or 000 on transport error
  local url="$1"
  shift
  curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$@" "$url" || true
}

http_body() { # http_body URL [curl args...]
  local url="$1"
  shift
  curl -s --max-time 15 "$@" "$url" || true
}

expect_reject() { # expect_reject LABEL STATUS
  case "$2" in
    401|403) log "probe OK   $1 -> HTTP $2 (rejected)" ;;
    000|"") fail "probe FAIL $1 -> transport error / endpoint unreachable" ;;
    *) fail "probe FAIL $1 -> HTTP $2 (expected 401/403; endpoint may be unauthenticated)" ;;
  esac
}

json_field() { # json_field BODY KEY -> value (first match)
  printf '%s' "$1" | sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -1
}

ids_in_body() { # ids_in_body BODY -> list of "id":"..." values
  printf '%s' "$1" | grep -oE '"id"[[:space:]]*:[[:space:]]*"[^"]+"' | LC_ALL=C sort -u || true
}

cmd_probe_auth() {
  [ $# -ge 1 ] || die "usage: $0 probe-auth BASE_URL [--path /api/v1/session] [--mode strict|dev-bypass] [--require-tls] [--insecure]"
  local base_url="$1"
  shift
  local probe_path="/api/v1/session" mode="strict" require_tls=0 insecure=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --path) [ $# -ge 2 ] || die "--path requires a value"; probe_path="$2"; shift 2 ;;
      --mode) [ $# -ge 2 ] || die "--mode requires a value"; mode="$2"; shift 2 ;;
      --require-tls) require_tls=1; shift ;;
      --insecure) insecure="-k"; shift ;;
      *) die "unknown option: $1" ;;
    esac
  done
  case "$mode" in
    strict|dev-bypass) ;;
    *) die "--mode must be strict or dev-bypass" ;;
  esac
  require_cmd curl

  local url="$base_url$probe_path"
  log "probe-auth against $url (mode=$mode)"

  if [ "$require_tls" = "1" ]; then
    case "$base_url" in
      https://*) log "probe OK   TLS required and base URL is https" ;;
      *) fail "probe FAIL --require-tls but base URL is not https: $base_url" ;;
    esac
  fi

  # 1. anonymous
  local st
  st="$(http_status "$url" $insecure)"
  expect_reject "anonymous request" "$st"

  # 2. forged bearer token (unsigned junk)
  st="$(http_status "$url" $insecure -H 'Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.forged.payload.forged.signature')"
  expect_reject "forged bearer token" "$st"

  # 3. forged identity headers with a VALID high-privilege role
  local tenant_a="00000000-0000-7000-8000-000000001111"
  local tenant_b="00000000-0000-7000-8000-000000009999"
  local dev_headers_a=(-H "X-Tenant-Id: $tenant_a" -H 'X-User-Id: 00000000-0000-7000-8000-000000002206' -H 'X-Roles: security_admin' -H 'X-MFA: true')
  st="$(http_status "$url" $insecure "${dev_headers_a[@]}")"
  if [ "$mode" = "strict" ]; then
    case "$st" in
      401|403) log "probe OK   forged role headers -> HTTP $st (rejected)" ;;
      *) fail "probe FAIL forged X-Roles: security_admin headers -> HTTP $st. Dev identity-header bypass is ACCEPTING forged roles; this posture must never be internet-facing (see docs/runbooks/fleet-deploy.md)" ;;
    esac
  else
    case "$st" in
      200) warn "dev-bypass posture confirmed: forged dev headers authenticate ($st). Acceptable ONLY behind an auth wall on a private staging network." ;;
      401|403) fail "probe FAIL dev-bypass mode expected dev headers to authenticate, got HTTP $st (is the target actually in OIDC/strict mode? rerun with --mode strict)" ;;
      *) fail "probe FAIL dev headers -> unexpected HTTP $st" ;;
    esac
  fi

  # 4. malformed role names must never authenticate (both modes)
  st="$(http_status "$url" $insecure -H "X-Tenant-Id: $tenant_a" -H 'X-User-Id: 00000000-0000-7000-8000-000000002206' -H 'X-Roles: admin,superuser' -H 'X-MFA: true')"
  expect_reject "forged headers with invalid role names" "$st"

  # 5. cross-tenant boundary on the device list
  local devices_path="/api/v1/devices"
  local body_a body_b st_a st_b
  st_a="$(http_status "$base_url$devices_path" $insecure -H "X-Tenant-Id: $tenant_a" -H 'X-User-Id: 00000000-0000-7000-8000-000000002206' -H 'X-Roles: device_operator' -H 'X-MFA: true')"
  if [ "$st_a" = "200" ]; then
    body_a="$(http_body "$base_url$devices_path" $insecure -H "X-Tenant-Id: $tenant_a" -H 'X-User-Id: 00000000-0000-7000-8000-000000002206' -H 'X-Roles: device_operator' -H 'X-MFA: true')"
    st_b="$(http_status "$base_url$devices_path" $insecure -H "X-Tenant-Id: $tenant_b" -H 'X-User-Id: 00000000-0000-7000-8000-000000009998' -H 'X-Roles: device_operator' -H 'X-MFA: true')"
    body_b="$(http_body "$base_url$devices_path" $insecure -H "X-Tenant-Id: $tenant_b" -H 'X-User-Id: 00000000-0000-7000-8000-000000009998' -H 'X-Roles: device_operator' -H 'X-MFA: true')"
    local leak=0 id
    if [ -n "$body_a" ] && [ "$body_a" != "[]" ]; then
      for id in $(ids_in_body "$body_a"); do
        case "
$(ids_in_body "$body_b")" in
          *"$id"*) leak=1; fail "probe FAIL cross-tenant leak: tenant B response contains tenant A device $id" ;;
        esac
      done
      [ "$leak" = "0" ] && log "probe OK   cross-tenant device list disjoint (tenant A data not visible to tenant B)"
    else
      log "probe SKIP cross-tenant: tenant A has no seeded devices to assert against (use dev seed or staging data)"
    fi
  else
    case "$st_a" in
      401|403) log "probe OK   device list not accessible without credentials (HTTP $st_a)" ;;
      *) warn "device list returned HTTP $st_a; cross-tenant probe skipped" ;;
    esac
  fi

  if [ "$FAILURES" -gt 0 ]; then
    log "probe-auth FAILED ($FAILURES failing probe group(s))"
    exit 1
  fi
  log "probe-auth PASSED (mode=$mode)"
  exit 0
}

# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------
cmd_version() {
  [ $# -ge 1 ] || die "usage: $0 version BASE_URL [--compose-dir DIR] [--require-build]"
  local base_url="$1"
  shift
  local compose_dir="" require_build=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --compose-dir) [ $# -ge 2 ] || die "--compose-dir requires a value"; compose_dir="$2"; shift 2 ;;
      --require-build) require_build=1; shift ;;
      *) die "unknown option: $1" ;;
    esac
  done
  require_cmd curl

  local path body st build_id=""
  for path in /health/live /health/ready /healthz; do
    st="$(http_status "$base_url$path" 2>/dev/null || true)"
    if [ "$st" = "200" ]; then
      body="$(http_body "$base_url$path" 2>/dev/null || true)"
      log "health OK  $path -> $body"
      local key found=""
      for key in buildSha gitSha build version commit; do
        found="$(json_field "$body" "$key")"
        if [ -n "$found" ]; then
          build_id="$key=$found"
          break
        fi
      done
    else
      warn "health endpoint $path -> HTTP ${st:-unreachable} at $base_url"
    fi
  done

  if [ -n "${BUILD_SHA:-}" ]; then
    log "local BUILD_SHA env: $BUILD_SHA"
    [ -z "$build_id" ] && build_id="env:BUILD_SHA=$BUILD_SHA"
  fi

  if [ -n "$compose_dir" ] && [ -d "$compose_dir" ]; then
    if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
      local injected
      injected="$(cd "$compose_dir" && docker compose config 2>/dev/null | grep -E 'BUILD_SHA' | head -3 || true)"
      if [ -n "$injected" ]; then
        log "compose BUILD_SHA wiring: $(printf '%s' "$injected" | tr '\n' ' ')"
        [ -z "$build_id" ] && build_id="compose:BUILD_SHA"
      else
        warn "compose dir $compose_dir has no BUILD_SHA in resolved config"
      fi
    else
      warn "docker daemon unavailable; cannot resolve compose BUILD_SHA from $compose_dir"
    fi
  fi

  if [ -n "$build_id" ]; then
    log "build identity resolved: $build_id"
  else
    warn "build identity NOT discoverable: /health endpoints return no build/git field (known gap: service-side wiring pending; env BUILD_SHA is injected by infra/compose/staging and documented in docs/runbooks/fleet-deploy.md)"
    [ "$require_build" = "1" ] && fail "--require-build set and no build identity found"
  fi

  if [ "$FAILURES" -gt 0 ]; then exit 1; fi
  exit 0
}

# ---------------------------------------------------------------------------
case "${1:-}" in
  backup) shift; cmd_backup "$@" ;;
  restore-verify) shift; cmd_restore_verify "$@" ;;
  probe-auth) shift; cmd_probe_auth "$@" ;;
  version) shift; cmd_version "$@" ;;
  -h|--help|help|'') usage ;;
  *) die "unknown subcommand: $1 (use -h)" ;;
esac
