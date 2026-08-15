# No-Code Architects Toolkit for Railway

A Railway-first deployment of the [No-Code Architects Toolkit](https://github.com/stephengpope/no-code-architects-toolkit): FFmpeg/media processing, transcription, screenshots, file conversion and automation APIs in one self-hosted service.

This repository does **not** fork or vendor the upstream application. The Docker build fetches an exact upstream Git commit, then creates a Railway-oriented CPU image around it. Upstream remains the application source of truth while this repository owns deployment, storage integration, reproducibility and runtime validation.

## Why this wrapper exists

A good Railway template needs a few guarantees that the generic upstream deployment does not provide:

- predictable `PORT` handling instead of a hard-coded listener;
- a dedicated unauthenticated `/healthz` endpoint for Railway deploy healthchecks;
- a generated API key instead of asking users to invent one;
- conservative worker/queue defaults for CPU-heavy media jobs;
- native Railway Bucket support for endpoints that need S3 storage;
- private-bucket compatibility using presigned result URLs instead of `public-read` ACLs;
- an exact upstream source revision instead of a moving image tag;
- **CPU-only PyTorch**, so Railway deployments do not ship unused NVIDIA/CUDA libraries;
- automated checks that verify Whisper, Chromium and the expected FFmpeg capabilities at runtime.

The intended Railway template is just **one application service + one Railway Bucket**. No Traefik, database, Redis, or reverse proxy is required.

## Local quick start

You need Docker with Compose v2.

```bash
cp .env.example .env
```

Change `API_KEY` in `.env`, then:

```bash
docker compose up -d --build
./scripts/runtime-contract.sh
./scripts/smoke-test.sh
```

Or with Make:

```bash
make up
make runtime-contract
make smoke
```

The API is available at `http://localhost:8080` by default.

The first build still downloads FFmpeg dependencies, a CPU PyTorch wheel, the Whisper `base` model and Chromium, so it is intentionally heavier than a normal web API build. It no longer inherits the upstream CUDA/NVIDIA image.

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

## What this repository changes

The upstream application source is fetched during the Docker build at the commit declared by `NCA_UPSTREAM_COMMIT`. This repository then:

1. installs PyTorch from the official CPU-only wheel index;
2. installs the upstream Python dependencies, Whisper and Playwright Chromium;
3. uses the distribution FFmpeg build instead of compiling a GPU-oriented monolithic image;
4. starts Gunicorn on `$PORT`;
5. registers `/healthz`;
6. replaces the upstream S3 upload function at process startup when Railway Bucket compatibility is needed.

For normal non-Railway S3 providers, upstream-style public URL behavior remains available. For Railway Buckets, uploads intentionally omit the public ACL assumption and return a time-limited presigned URL instead.

## Security

This service should be considered privileged. NCA Toolkit includes a Python execution API in addition to media-processing endpoints, so do not expose it with a weak or missing key.

Read [`SECURITY.md`](SECURITY.md) before publishing a public template.

## Updating upstream

The Dockerfile pins the application source explicitly:

```dockerfile
ARG NCA_UPSTREAM_COMMIT=d9bb5679e203e6b5d3b3c2b9ab848a289c645024
```

Do not point this at a branch or `latest`. Update the SHA intentionally, review the upstream diff, then let CI rebuild the image and verify the runtime contract before merging.

PyTorch is also intentionally pinned and installed through the CPU wheel index. Dependabot monitors Docker base images and GitHub Actions; application-source revisions remain a deliberate update because they can change API behavior.

## Validation

Run the same fast lint, unit-test, and configuration checks used by CI:

```bash
make check
```

CI runs Ruff, Ruff formatting checks, yamllint, ShellCheck, unit tests on Python 3.10 and 3.14, Docker Compose validation, and Dockerfile build checks.

The runtime workflow additionally builds the real Railway image and checks:

- PyTorch reports no CUDA runtime;
- the baked Whisper model exists;
- Playwright can locate Chromium;
- required FFmpeg codecs/filters are enabled;
- `/healthz` responds;
- a valid API key succeeds;
- an invalid API key is rejected.

After a local build:

```bash
make runtime-contract
make smoke
```

## Upstream

- Application: `stephengpope/no-code-architects-toolkit`
- Pinned source revision: see `NCA_UPSTREAM_COMMIT` in [`Dockerfile`](Dockerfile)
- Upstream license: GNU GPL v2

This project is an independent Railway deployment wrapper and is not an official No-Code Architects project.

## License

GNU GPL v2. See [`LICENSE`](LICENSE).
