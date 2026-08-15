"""Railway-specific application shim for NCA Toolkit."""

from __future__ import annotations


def _should_patch_s3() -> bool:
    from railway_storage import should_enable_s3_compat

    return should_enable_s3_compat()


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
