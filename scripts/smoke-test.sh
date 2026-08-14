#!/usr/bin/env bash
set -Eeuo pipefail

PORT="${PORT:-8080}"
BASE_URL="${BASE_URL:-http://127.0.0.1:${PORT}}"
API_KEY="${API_KEY:-local-development-key-change-me}"
ATTEMPTS="${SMOKE_ATTEMPTS:-60}"

printf 'Waiting for %s/healthz' "$BASE_URL"
for ((i = 1; i <= ATTEMPTS; i++)); do
  if curl --silent --fail --max-time 2 "$BASE_URL/healthz" >/dev/null; then
    printf '\nHealthcheck: OK\n'
    break
  fi
  if [[ "$i" -eq "$ATTEMPTS" ]]; then
    printf '\nERROR: service did not become healthy after %s attempts\n' "$ATTEMPTS" >&2
    exit 1
  fi
  printf '.'
  sleep 2
done

curl --silent --fail --max-time 10 \
  -H "X-API-Key: ${API_KEY}" \
  "$BASE_URL/v1/toolkit/authenticate" >/dev/null
printf 'Authenticated API request: OK\n'

status="$({ curl --silent --output /dev/null --write-out '%{http_code}' --max-time 10 \
  -H 'X-API-Key: definitely-wrong' \
  "$BASE_URL/v1/toolkit/authenticate"; } || true)"
if [[ "$status" != "401" ]]; then
  echo >&2 "ERROR: invalid API key returned HTTP ${status:-<none>} instead of 401"
  exit 1
fi
printf 'Invalid API key rejected: OK\n'
printf 'Smoke test passed.\n'
