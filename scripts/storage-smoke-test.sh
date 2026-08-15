#!/usr/bin/env bash
set -Eeuo pipefail

PORT="${PORT:-8080}"
BASE_URL="${BASE_URL:-http://127.0.0.1:${PORT}}"
API_KEY="${API_KEY:-ci-local-development-key-change-me}"

payload="$(
  curl --silent --show-error --fail --max-time 30 \
    -H "X-API-Key: ${API_KEY}" \
    "${BASE_URL}/v1/toolkit/test"
)"

result_url="$(
  printf '%s' "$payload" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
code = payload.get("code")
if code != 200:
    raise SystemExit(f"unexpected API code: {code}")
url = payload.get("response")
if not isinstance(url, str) or not url:
    raise SystemExit("missing response URL")
print(url)
'
)"

if [[ "$result_url" != *"X-Amz-Algorithm="* || "$result_url" != *"X-Amz-Signature="* ]]; then
  echo >&2 "ERROR: storage result is not a presigned S3 URL: $result_url"
  exit 1
fi

tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

curl --silent --show-error --fail --location --max-time 30 \
  "$result_url" \
  --output "$tmp_file"

if ! grep --fixed-strings --quiet \
  "You have successfully installed the NCA Toolkit API, great job!" \
  "$tmp_file"; then
  echo >&2 "ERROR: downloaded object did not contain the expected toolkit test payload"
  exit 1
fi

printf 'S3 upload: OK\n'
printf 'Presigned URL: OK\n'
printf 'Presigned HTTP download: OK\n'
printf 'Storage smoke test passed.\n'
