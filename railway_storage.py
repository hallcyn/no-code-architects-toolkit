"""S3 compatibility helpers for Railway-hosted NCA Toolkit.

Upstream NCA Toolkit assumes an S3-compatible bucket can accept the
``public-read`` ACL and that returned objects are publicly readable.
Railway Buckets are private, so this adapter uploads without an ACL and
returns a presigned URL instead.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import boto3
from botocore.config import Config

RAILWAY_STORAGE_HOST = "storage.railway.app"
RAILWAY_STORAGEAPI_SUFFIX = ".storageapi.dev"
AWS_MAX_PRESIGN_EXPIRY_SECONDS = 7 * 24 * 60 * 60
RAILWAY_MAX_PRESIGN_EXPIRY_SECONDS = 90 * 24 * 60 * 60
DEFAULT_PRESIGN_EXPIRY_SECONDS = 7 * 24 * 60 * 60


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_railway_storage_endpoint(endpoint: str) -> bool:
    """Return whether an S3 endpoint belongs to Railway Buckets.

    Railway documents ``storage.railway.app`` as the canonical endpoint, while
    deployed buckets can also expose regional ``*.storageapi.dev`` endpoints.
    Support both so private-object handling does not depend on one hostname.
    """

    hostname = (urlsplit(endpoint).hostname or "").lower()
    return (
        hostname == RAILWAY_STORAGE_HOST
        or hostname.endswith(f".{RAILWAY_STORAGE_HOST}")
        or hostname == RAILWAY_STORAGEAPI_SUFFIX.removeprefix(".")
        or hostname.endswith(RAILWAY_STORAGEAPI_SUFFIX)
    )


def should_enable_s3_compat() -> bool:
    """Return whether the Railway/private-S3 adapter should patch upstream."""

    return (
        is_railway_storage_endpoint(os.getenv("S3_ENDPOINT_URL", ""))
        or _truthy(os.getenv("S3_RETURN_PRESIGNED_URL"))
        or _truthy(os.getenv("NCA_S3_COMPAT_MODE"))
    )


def _client(*, endpoint: str, access_key: str, secret_key: str, region: str, addressing_style: str):
    session = boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    return session.client(
        "s3",
        endpoint_url=endpoint,
        config=Config(s3={"addressing_style": addressing_style}, signature_version="s3v4"),
    )


def _public_object_url(endpoint: str, bucket: str, key: str, addressing_style: str) -> str:
    endpoint = endpoint.rstrip("/")
    encoded_key = quote(key)
    if addressing_style == "virtual":
        parts = urlsplit(endpoint)
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
        return urlunsplit((parts.scheme, f"{bucket}.{host}{port}", f"/{encoded_key}", "", ""))
    return f"{endpoint}/{quote(bucket)}/{encoded_key}"


def _presign_expiry(*, railway_storage: bool) -> int:
    raw = os.getenv("S3_PRESIGNED_URL_EXPIRY", str(DEFAULT_PRESIGN_EXPIRY_SECONDS))
    try:
        expiry = int(raw)
    except ValueError as exc:
        raise ValueError("S3_PRESIGNED_URL_EXPIRY must be an integer number of seconds") from exc

    max_expiry = (
        RAILWAY_MAX_PRESIGN_EXPIRY_SECONDS if railway_storage else AWS_MAX_PRESIGN_EXPIRY_SECONDS
    )
    if expiry < 60 or expiry > max_expiry:
        raise ValueError(f"S3_PRESIGNED_URL_EXPIRY must be between 60 and {max_expiry} seconds")
    return expiry


def upload_to_s3(file_path, s3_url, access_key, secret_key, bucket_name, region):
    """Drop-in replacement for upstream ``services.s3_toolkit.upload_to_s3``.

    Railway Buckets are uploaded without a public ACL and return a time-limited
    signed GET URL. Other S3 providers keep upstream-style public URL behavior
    unless ``S3_RETURN_PRESIGNED_URL=true`` is explicitly configured.
    """

    endpoint = str(s3_url).rstrip("/")
    railway_storage = is_railway_storage_endpoint(endpoint)

    addressing_style = os.getenv("S3_ADDRESSING_STYLE", "").strip().lower()
    if addressing_style not in {"path", "virtual"}:
        addressing_style = "virtual" if railway_storage else "path"

    use_presigned = _truthy(
        os.getenv("S3_RETURN_PRESIGNED_URL"),
        default=railway_storage,
    )

    upload_client = _client(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        region=region or "auto",
        addressing_style=addressing_style,
    )

    key = Path(file_path).name
    upload_acl = os.getenv("S3_UPLOAD_ACL", "").strip()
    extra_args = {"ACL": upload_acl} if upload_acl and not railway_storage else None

    with open(file_path, "rb") as data:
        if extra_args:
            upload_client.upload_fileobj(data, bucket_name, key, ExtraArgs=extra_args)
        else:
            upload_client.upload_fileobj(data, bucket_name, key)

    if not use_presigned:
        return _public_object_url(endpoint, bucket_name, key, addressing_style)

    expiry = _presign_expiry(railway_storage=railway_storage)

    # Useful for local MinIO: upload via an internal hostname, but sign URLs
    # against a host that the developer's browser can actually reach.
    public_endpoint = os.getenv("S3_PUBLIC_ENDPOINT_URL", endpoint).rstrip("/")
    signing_client = upload_client
    if public_endpoint != endpoint:
        signing_client = _client(
            endpoint=public_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            region=region or "auto",
            addressing_style=addressing_style,
        )

    return signing_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name, "Key": key},
        ExpiresIn=expiry,
    )
