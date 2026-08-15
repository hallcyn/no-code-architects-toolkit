"""Railway-specific application shim for NCA Toolkit."""

from __future__ import annotations

import os


def _truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


def _should_patch_s3() -> bool:
    endpoint = os.getenv("S3_ENDPOINT_URL", "").lower()
    return "storage.railway.app" in endpoint or _truthy(os.getenv("NCA_S3_COMPAT_MODE"))


# Patch before importing the upstream Flask app. ``services.cloud_storage``
# imports this function while NCA blueprints are discovered, so doing it here
# keeps the rest of the upstream code untouched.
if _should_patch_s3():
    from services import s3_toolkit

    from railway_storage import upload_to_s3

    s3_toolkit.upload_to_s3 = upload_to_s3

from app import app as app


@app.get("/healthz")
def railway_healthcheck():
    """Unauthenticated liveness endpoint for Railway's deployment healthcheck."""
    return {"status": "ok", "service": "no-code-architects-toolkit"}, 200
