# No-Code Architects Toolkit for Railway

A Railway-first deployment wrapper for the [No-Code Architects Toolkit](https://github.com/stephengpope/no-code-architects-toolkit): FFmpeg/media processing, transcription, screenshots, file conversion and automation APIs in one self-hosted service.

This repository does **not** fork or vendor the upstream application. It layers a small amount of Railway-specific behavior on top of the official Docker image so deployments stay simple and upstream remains the source of truth.

## Why this wrapper exists

The upstream Docker deployment works, but a good Railway template needs a few extra guarantees:

- predictable `PORT` handling instead of a hard-coded listener;
- a dedicated unauthenticated `/healthz` endpoint for Railway deploy healthchecks;
- a generated API key instead of asking users to invent one;
- conservative worker/queue defaults for CPU-heavy media jobs;
- native Railway Bucket support for endpoints that need S3 storage;
- private-bucket compatibility using presigned result URLs instead of `public-read` ACLs;
- a reproducible upstream image pinned by digest.

The intended Railway template is just **one application service + one Railway Bucket**. No Traefik, database, Redis, or reverse proxy is required.

## Local quick start

You need Docker with Compose v2.

```bash
cp .env.example .env
```

Change `API_KEY` in `.env`, then:

```bash
docker compose up -d --build
./scripts/smoke-test.sh
```

Or with Make:

```bash
make up
make smoke
```

The API is available at `http://localhost:8080` by default.

> The upstream image is large because it contains FFmpeg/codecs, Whisper and Chromium. The first Docker pull/build is therefore much heavier than a normal web API image; subsequent builds reuse the local image cache.

### Verify manually

Healthcheck:

```bash
curl http://localhost:8080/healthz
```

Authentication:

```bash
curl \
  -H "X-API-Key: $API_KEY" \
  http://localhost:8080/v1/toolkit/authenticate
```

## Railway deployment model

The published template should create:

```text
Internet
   |
   v
nca-toolkit  ---- S3 API ---->  nca-storage (Railway Bucket)
   |
   +-- generated API_KEY
   +-- /healthz
   +-- NCA Toolkit API
```

Railway can generate secrets at template-deploy time and expose Railway Bucket credentials through reference variables, so users should not need to manually configure storage credentials.

The exact composer configuration is documented in [`docs/railway-template.md`](docs/railway-template.md).

## Environment variables

### Core

| Variable | Default | Purpose |
| --- | --- | --- |
| `API_KEY` | none | **Required.** Protects the NCA API. Generate a strong random value. |
| `PORT` | `8080` | HTTP listen port. Railway template pins this to `8080`. |
| `GUNICORN_WORKERS` | `1` | Gunicorn worker count. One is the safe default for heavy media workloads. |
| `GUNICORN_TIMEOUT` | `600` | Worker timeout in seconds. |
| `GUNICORN_KEEPALIVE` | `80` | Gunicorn keep-alive in seconds. |
| `MAX_QUEUE_LENGTH` | `5` | Maximum upstream in-process queue depth. |
| `LOCAL_STORAGE_PATH` | `/tmp/nca-toolkit` | Temporary workspace and upstream job-status files. |

### S3 / Railway Bucket

Most endpoints that create files need an S3-compatible or GCP storage provider. The Railway template wires a Railway Bucket automatically.

| Variable | Purpose |
| --- | --- |
| `S3_ENDPOINT_URL` | S3-compatible API endpoint. |
| `S3_ACCESS_KEY` | S3 access key. |
| `S3_SECRET_KEY` | S3 secret key. |
| `S3_BUCKET_NAME` | S3 bucket name. |
| `S3_REGION` | S3 region (`auto` on Railway). |
| `S3_RETURN_PRESIGNED_URL` | Return a signed GET URL after upload. Automatically enabled for Railway Buckets. |
| `S3_PRESIGNED_URL_EXPIRY` | Signed URL lifetime in seconds. Defaults to 7 days; Railway Buckets allow up to 90 days. |
| `S3_ADDRESSING_STYLE` | `virtual` for current Railway Buckets; `path` for providers that require path-style access. |
| `S3_PUBLIC_ENDPOINT_URL` | Advanced: alternate endpoint used only when generating signed URLs, useful for local MinIO. |
| `S3_UPLOAD_ACL` | Advanced: optional ACL for non-Railway S3 providers. Never applied to Railway Buckets. |
| `NCA_S3_COMPAT_MODE` | Force this wrapper's S3 adapter for a non-Railway endpoint. |

## What the wrapper changes

The upstream application code remains in the official Docker image. This repo only:

1. starts Gunicorn on `$PORT`;
2. registers `/healthz`;
3. replaces the upstream S3 upload function at process startup when Railway Bucket compatibility is needed.

For normal non-Railway S3 providers, upstream behavior remains available. For Railway Buckets, uploads intentionally omit the unsupported/public ACL assumption and return a time-limited presigned URL instead.

## Security

This service should be considered privileged. NCA Toolkit includes a Python execution API in addition to media-processing endpoints, so do not expose it with a weak or missing key.

Read [`SECURITY.md`](SECURITY.md) before publishing a public template.

## Updating upstream

The Dockerfile pins the official image by digest:

```dockerfile
FROM stephengpope/no-code-architects-toolkit:latest@sha256:...
```

This prevents an upstream `latest` push from silently changing every new deployment. Dependabot is configured to propose Docker updates monthly; review and smoke-test those updates before merging.

## Validation

Run the same fast lint, unit-test, and configuration checks used by CI:

```bash
make check
```

CI runs Ruff, Ruff formatting checks, yamllint, ShellCheck, unit tests on Python 3.10 and 3.14, Docker Compose validation, and Dockerfile build checks. A separate runtime workflow boots the real pinned upstream image for wrapper changes and on a weekly schedule.

Runtime smoke test after `docker compose up`:

```bash
make smoke
```

The smoke test verifies health, a valid API key, and rejection of an invalid API key.

## Upstream

- Application: `stephengpope/no-code-architects-toolkit`
- Official image: `stephengpope/no-code-architects-toolkit`
- Upstream license: GNU GPL v2

This project is an independent Railway deployment wrapper and is not an official No-Code Architects project.

## License

GNU GPL v2. See [`LICENSE`](LICENSE).
