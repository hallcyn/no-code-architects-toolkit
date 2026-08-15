# Changelog

## Unreleased

- Recognize Railway regional `*.storageapi.dev` Bucket endpoints and enable the private-S3 compatibility adapter whenever presigned result URLs are requested, preventing generated files from being returned as inaccessible private object URLs.

## 0.1.0 - 2026-08-15

- Initial Railway-first packaging of the No-Code Architects Toolkit.
- Pinned the exact upstream source commit for reproducible application code.
- Replaced the oversized upstream CUDA/NVIDIA image with a CPU-native Railway image using the official PyTorch CPU wheel index.
- Added Debian FFmpeg, the baked Whisper `base` model, and Playwright Chromium.
- Added dynamic Railway `PORT` binding and conservative Gunicorn defaults.
- Added unauthenticated `/healthz` endpoint for Railway deployment healthchecks.
- Added Railway Bucket compatibility with private S3 uploads and presigned result URLs.
- Added a runtime contract that verifies CPU-only Torch, Whisper, Chromium, and required FFmpeg features.
- Added local Docker Compose workflow, unit tests, Ruff/format/yamllint/ShellCheck CI, Docker config validation, runtime Docker smoke CI, Dependabot, and template-author documentation.
