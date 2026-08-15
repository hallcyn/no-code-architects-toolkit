#!/usr/bin/env bash
set -Eeuo pipefail

service="${1:-nca-toolkit}"

compose_exec() {
  docker compose exec -T "$service" "$@"
}

echo "Checking CPU-only Python runtime..."
compose_exec python - <<'PY'
import importlib.util

import torch
import whisper

assert torch.version.cuda is None, f"CUDA-enabled torch detected: {torch.version.cuda}"
assert not torch.cuda.is_available(), "CUDA unexpectedly available"
assert importlib.util.find_spec("playwright") is not None, "playwright package missing"
assert whisper.available_models(), "Whisper model registry is empty"
print(f"torch={torch.__version__} cuda={torch.version.cuda}")
PY

echo "Checking baked Whisper model..."
compose_exec python - <<'PY'
import os
from pathlib import Path

cache = Path(os.environ["WHISPER_CACHE_DIR"])
models = list(cache.glob("*.pt"))
assert models, f"No Whisper model found in {cache}"
print("whisper_models=" + ",".join(path.name for path in models))
PY

echo "Checking Playwright Chromium..."
compose_exec python - <<'PY'
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    executable = Path(playwright.chromium.executable_path)
    assert executable.exists(), f"Chromium executable missing: {executable}"
    print(f"chromium={executable}")
PY

echo "Checking FFmpeg capabilities..."
ffmpeg_build="$(compose_exec ffmpeg -hide_banner -buildconf 2>&1)"
for feature in libx264 libx265 libvpx libwebp libmp3lame libopus libvorbis libass libfreetype libsrt; do
  if ! grep -q -- "--enable-${feature}" <<<"$ffmpeg_build"; then
    echo >&2 "ERROR: FFmpeg is missing --enable-${feature}"
    exit 1
  fi
done

filters="$(compose_exec ffmpeg -hide_banner -filters 2>&1)"
grep -q '[[:space:]]drawtext[[:space:]]' <<<"$filters" || {
  echo >&2 "ERROR: FFmpeg drawtext filter is unavailable"
  exit 1
}

echo "Runtime contract passed."
