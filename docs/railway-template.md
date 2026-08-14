# Railway template setup

This repository is intentionally only the application wrapper. The public Railway template should compose two Railway resources so end users do not have to bring their own object storage.

## Resources

1. `nca-toolkit` — GitHub service using this repository.
2. `nca-storage` — Railway Bucket in the same project/environment.

The upstream toolkit needs S3/GCP storage for many endpoints that generate files. Railway Buckets are S3-compatible and expose credentials as reference variables, so the template can wire everything automatically.

## nca-toolkit settings

- Source: `https://github.com/hallcyn/no-code-architects-toolkit`
- Builder: Dockerfile (picked up from `railway.json`)
- Public networking: HTTP enabled
- Target port: `8080`
- Healthcheck: `/healthz`
- Replicas: `1` by default

## Variables

Configure these directly in the Railway template composer.

| Variable | Template value | Required | Notes |
| --- | --- | --- | --- |
| `API_KEY` | `${{secret(48)}}` | yes | Generate automatically. Seal it in the template. |
| `PORT` | `8080` | yes | Explicit target port for predictable networking. |
| `GUNICORN_WORKERS` | `1` | yes | Safe default for CPU/RAM-heavy media processing. |
| `GUNICORN_TIMEOUT` | `600` | yes | Allows longer synchronous media jobs. |
| `GUNICORN_KEEPALIVE` | `80` | yes | Matches the upstream deployment behavior. |
| `MAX_QUEUE_LENGTH` | `5` | yes | Prevents an accidentally unbounded in-process queue. |
| `LOCAL_STORAGE_PATH` | `/tmp/nca-toolkit` | yes | Ephemeral workspace and job metadata. |
| `S3_ENDPOINT_URL` | `${{nca-storage.ENDPOINT}}` | yes | Railway Bucket endpoint. |
| `S3_ACCESS_KEY` | `${{nca-storage.ACCESS_KEY_ID}}` | yes | Railway Bucket credential. |
| `S3_SECRET_KEY` | `${{nca-storage.SECRET_ACCESS_KEY}}` | yes | Railway Bucket credential. |
| `S3_BUCKET_NAME` | `${{nca-storage.BUCKET}}` | yes | S3 API bucket name, not the display name. |
| `S3_REGION` | `${{nca-storage.REGION}}` | yes | Railway currently exposes `auto`. |
| `S3_RETURN_PRESIGNED_URL` | `true` | yes | Railway Buckets are private. |
| `S3_PRESIGNED_URL_EXPIRY` | `604800` | yes | 7-day default. Railway currently supports presigned URLs up to 90 days. |
| `S3_ADDRESSING_STYLE` | `virtual` | yes | Railway's current bucket URL style. |

Do **not** ask users to paste bucket credentials manually. The whole point of this template is that the reference variables above are created with the deployment.

## Template description

Suggested short description:

> Self-host the No-Code Architects Toolkit API for FFmpeg, media conversion, transcription, screenshots and automation workflows. Includes secure API auth and Railway object storage out of the box.

Suggested tags: `automation`, `n8n`, `media`, `ffmpeg`, `api`, `self-hosted`.

## Before publishing

- Deploy the template into a fresh Railway project, not an existing development project.
- Confirm `/healthz` is green without an API key header.
- Call `/v1/toolkit/authenticate` with the generated `API_KEY` and verify HTTP 200.
- Run one file-producing endpoint and verify the returned URL is a working presigned Railway Bucket URL.
- Confirm a wrong API key returns HTTP 401.
- Confirm the service remains single-replica unless upstream queueing is redesigned for distributed workers.
