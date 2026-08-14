from __future__ import annotations

from dataclasses import dataclass, field

import pytest

import railway_storage


@dataclass
class FakeS3Client:
    uploads: list[dict] = field(default_factory=list)
    presigns: list[dict] = field(default_factory=list)

    def upload_fileobj(self, data, bucket, key, ExtraArgs=None):  # noqa: N803
        self.uploads.append(
            {
                "content": data.read(),
                "bucket": bucket,
                "key": key,
                "extra_args": ExtraArgs,
            }
        )

    def generate_presigned_url(self, operation, *, Params, ExpiresIn):  # noqa: N803
        self.presigns.append(
            {"operation": operation, "params": Params, "expires_in": ExpiresIn}
        )
        return "https://signed.example/result"


def test_truthy_values():
    for value in ("1", "true", "TRUE", " yes ", "on"):
        assert railway_storage._truthy(value)
    for value in (None, "", "0", "false", "no", "off"):
        assert not railway_storage._truthy(value)


def test_railway_upload_defaults_to_private_presigned_url(tmp_path, monkeypatch):
    file_path = tmp_path / "hello world.txt"
    file_path.write_bytes(b"payload")
    client = FakeS3Client()
    calls = []

    def fake_client(**kwargs):
        calls.append(kwargs)
        return client

    monkeypatch.setattr(railway_storage, "_client", fake_client)
    monkeypatch.delenv("S3_RETURN_PRESIGNED_URL", raising=False)
    monkeypatch.delenv("S3_ADDRESSING_STYLE", raising=False)
    monkeypatch.delenv("S3_UPLOAD_ACL", raising=False)
    monkeypatch.delenv("S3_PRESIGNED_URL_EXPIRY", raising=False)

    result = railway_storage.upload_to_s3(
        file_path,
        "https://storage.railway.app",
        "access",
        "secret",
        "bucket-123",
        "auto",
    )

    assert result == "https://signed.example/result"
    assert calls == [
        {
            "endpoint": "https://storage.railway.app",
            "access_key": "access",
            "secret_key": "secret",
            "region": "auto",
            "addressing_style": "virtual",
        }
    ]
    assert client.uploads == [
        {
            "content": b"payload",
            "bucket": "bucket-123",
            "key": "hello world.txt",
            "extra_args": None,
        }
    ]
    assert client.presigns[0]["expires_in"] == railway_storage.DEFAULT_PRESIGN_EXPIRY_SECONDS


def test_railway_ignores_public_acl(tmp_path, monkeypatch):
    file_path = tmp_path / "asset.bin"
    file_path.write_bytes(b"x")
    client = FakeS3Client()
    monkeypatch.setattr(railway_storage, "_client", lambda **_: client)
    monkeypatch.setenv("S3_UPLOAD_ACL", "public-read")

    railway_storage.upload_to_s3(
        file_path,
        "https://storage.railway.app",
        "access",
        "secret",
        "bucket",
        "auto",
    )

    assert client.uploads[0]["extra_args"] is None


def test_non_railway_provider_keeps_public_url_behavior(tmp_path, monkeypatch):
    file_path = tmp_path / "hello world.txt"
    file_path.write_bytes(b"payload")
    client = FakeS3Client()
    monkeypatch.setattr(railway_storage, "_client", lambda **_: client)
    monkeypatch.delenv("S3_RETURN_PRESIGNED_URL", raising=False)
    monkeypatch.setenv("S3_UPLOAD_ACL", "public-read")
    monkeypatch.setenv("S3_ADDRESSING_STYLE", "path")

    result = railway_storage.upload_to_s3(
        file_path,
        "https://objects.example.com/",
        "access",
        "secret",
        "media bucket",
        "eu-west-1",
    )

    assert result == "https://objects.example.com/media%20bucket/hello%20world.txt"
    assert client.uploads[0]["extra_args"] == {"ACL": "public-read"}
    assert not client.presigns


def test_presigned_url_can_use_a_separate_public_endpoint(tmp_path, monkeypatch):
    file_path = tmp_path / "asset.bin"
    file_path.write_bytes(b"payload")
    upload_client = FakeS3Client()
    signing_client = FakeS3Client()
    clients = iter([upload_client, signing_client])
    calls = []

    def fake_client(**kwargs):
        calls.append(kwargs)
        return next(clients)

    monkeypatch.setattr(railway_storage, "_client", fake_client)
    monkeypatch.setenv("S3_RETURN_PRESIGNED_URL", "true")
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT_URL", "http://localhost:9000")

    result = railway_storage.upload_to_s3(
        file_path,
        "http://minio:9000",
        "access",
        "secret",
        "bucket",
        "us-east-1",
    )

    assert result == "https://signed.example/result"
    assert calls[0]["endpoint"] == "http://minio:9000"
    assert calls[1]["endpoint"] == "http://localhost:9000"
    assert signing_client.presigns[0]["params"] == {"Bucket": "bucket", "Key": "asset.bin"}


@pytest.mark.parametrize(
    ("endpoint", "expiry", "maximum"),
    [
        ("https://s3.amazonaws.com", "59", railway_storage.AWS_MAX_PRESIGN_EXPIRY_SECONDS),
        (
            "https://storage.railway.app",
            str(railway_storage.RAILWAY_MAX_PRESIGN_EXPIRY_SECONDS + 1),
            railway_storage.RAILWAY_MAX_PRESIGN_EXPIRY_SECONDS,
        ),
    ],
)
def test_presign_expiry_is_bounded(tmp_path, monkeypatch, endpoint, expiry, maximum):
    file_path = tmp_path / "asset.bin"
    file_path.write_bytes(b"payload")
    monkeypatch.setattr(railway_storage, "_client", lambda **_: FakeS3Client())
    monkeypatch.setenv("S3_RETURN_PRESIGNED_URL", "true")
    monkeypatch.setenv("S3_PRESIGNED_URL_EXPIRY", expiry)

    with pytest.raises(ValueError, match=rf"between 60 and {maximum}"):
        railway_storage.upload_to_s3(
            file_path,
            endpoint,
            "access",
            "secret",
            "bucket",
            "us-east-1",
        )


def test_presign_expiry_must_be_an_integer(tmp_path, monkeypatch):
    file_path = tmp_path / "asset.bin"
    file_path.write_bytes(b"payload")
    monkeypatch.setattr(railway_storage, "_client", lambda **_: FakeS3Client())
    monkeypatch.setenv("S3_RETURN_PRESIGNED_URL", "true")
    monkeypatch.setenv("S3_PRESIGNED_URL_EXPIRY", "tomorrow")

    with pytest.raises(ValueError, match="integer number of seconds"):
        railway_storage.upload_to_s3(
            file_path,
            "https://storage.railway.app",
            "access",
            "secret",
            "bucket",
            "auto",
        )
