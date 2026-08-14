# Changelog

## 0.1.0 - 2026-08-14

- Initial Railway-first wrapper around the official NCA Toolkit Docker image.
- Pinned upstream image digest for reproducible deployments.
- Added dynamic Railway `PORT` binding and conservative Gunicorn defaults.
- Added unauthenticated `/healthz` endpoint for Railway deployment healthchecks.
- Added Railway Bucket compatibility with private S3 uploads and presigned result URLs.
- Added local Docker Compose workflow, unit tests, lint/config CI, runtime Docker smoke CI, Dependabot, and template-author documentation.
