#!/usr/bin/env bash
set -Eeuo pipefail

PORT="${PORT:-8080}"
BASE_URL="${BASE_URL:-http://127.0.0.1:${PORT}}"
ATTEMPTS="${SMOKE_ATTEMPTS:-60}"

# Docker Compose reads `.env` automatically, while a standalone shell script
# does not. For the default local smoke path, resolve the API key from the
# running Compose container so the test always exercises the credentials the
# service actually started with. Explicit API_KEY still wins for CI or remote
# smoke tests.
if [[ -n "${API_KEY:-}" ]]; then
  smoke_api_key="$API_KEY"
elif command -v docker >/dev/null 2>&1 \
  && docker compose ps --status running --quiet nca-toolkit 2>/dev/null | grep -q .; then
  smoke_api_key="$(docker compose exec -T nca-toolkit printenv API_KEY | tr -d '\r\n')"
else
  smoke_api_key="local-development-key-change-me"
fi

if [[ -z "$smoke_api_key" ]]; then
  echo >&2 "ERROR: API_KEY could not be resolved for the smoke test"
  exit 1
fi

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
  -H "X-API-Key: ${smoke_api_key}" \
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
