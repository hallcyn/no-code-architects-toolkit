#!/usr/bin/env bash
set -Eeuo pipefail

fail() {
  echo >&2 "ERROR: $*"
  exit 64
}

require_uint() {
  local name="$1"
  local value="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || fail "$name must be an unsigned integer, got '$value'."
}

if [[ -z "${API_KEY:-}" ]]; then
  fail "API_KEY is required. Set a strong random secret before starting NCA Toolkit."
fi

if (( ${#API_KEY} < 24 )); then
  fail "API_KEY must be at least 24 characters long."
fi

export PORT="${PORT:-8080}"
export GUNICORN_WORKERS="${GUNICORN_WORKERS:-1}"
export GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-600}"
export GUNICORN_KEEPALIVE="${GUNICORN_KEEPALIVE:-80}"
export MAX_QUEUE_LENGTH="${MAX_QUEUE_LENGTH:-5}"
export LOCAL_STORAGE_PATH="${LOCAL_STORAGE_PATH:-/tmp/nca-toolkit}"

require_uint PORT "$PORT"
require_uint GUNICORN_WORKERS "$GUNICORN_WORKERS"
require_uint GUNICORN_TIMEOUT "$GUNICORN_TIMEOUT"
require_uint GUNICORN_KEEPALIVE "$GUNICORN_KEEPALIVE"
require_uint MAX_QUEUE_LENGTH "$MAX_QUEUE_LENGTH"

(( PORT >= 1 && PORT <= 65535 )) || fail "PORT must be between 1 and 65535."
(( GUNICORN_WORKERS >= 1 )) || fail "GUNICORN_WORKERS must be at least 1."
(( GUNICORN_TIMEOUT >= 1 )) || fail "GUNICORN_TIMEOUT must be at least 1 second."

mkdir -p "$LOCAL_STORAGE_PATH"

echo "Starting NCA Toolkit on 0.0.0.0:${PORT} (workers=${GUNICORN_WORKERS}, timeout=${GUNICORN_TIMEOUT}s)"

exec gunicorn \
  --bind "0.0.0.0:${PORT}" \
  --workers "$GUNICORN_WORKERS" \
  --timeout "$GUNICORN_TIMEOUT" \
  --worker-class sync \
  --keep-alive "$GUNICORN_KEEPALIVE" \
  --config gunicorn.conf.py \
  railway_app:app
