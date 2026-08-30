from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import boto3  # type: ignore[import-untyped]
from botocore.client import Config  # type: ignore[import-untyped]

from media_service.config import Settings


@dataclass(frozen=True)
class ObjectHead:
    content_type: str
    size_bytes: int


class ObjectStorage(Protocol):
    def ensure_bucket(self) -> None: ...
    def create_upload_url(self, *, object_key: str, content_type: str, expires_in: int) -> str: ...
    def create_download_url(self, *, object_key: str, expires_in: int) -> str: ...
    def head(self, *, object_key: str) -> ObjectHead: ...
    def get_bytes(self, *, object_key: str) -> bytes: ...
    def put_bytes(self, *, object_key: str, content_type: str, data: bytes) -> None: ...
    def delete_objects(self, *, object_keys: Sequence[str]) -> None: ...


class S3ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        client_options = {
            "aws_access_key_id": settings.s3_access_key_id,
            "aws_secret_access_key": settings.s3_secret_access_key,
            "region_name": settings.s3_region,
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        }
        self._bucket = settings.s3_bucket
        self._internal = boto3.client("s3", endpoint_url=settings.s3_endpoint_url, **client_options)
        self._public = boto3.client(
            "s3", endpoint_url=settings.s3_public_endpoint_url, **client_options
        )

    def ensure_bucket(self) -> None:
        existing = {bucket["Name"] for bucket in self._internal.list_buckets()["Buckets"]}
        if self._bucket not in existing:
            self._internal.create_bucket(Bucket=self._bucket)

    def create_upload_url(self, *, object_key: str, content_type: str, expires_in: int) -> str:
        return str(
            self._public.generate_presigned_url(
                "put_object",
                Params={"Bucket": self._bucket, "Key": object_key, "ContentType": content_type},
                ExpiresIn=expires_in,
                HttpMethod="PUT",
            )
        )

    def create_download_url(self, *, object_key: str, expires_in: int) -> str:
        return str(
            self._public.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=expires_in,
            )
        )

    def head(self, *, object_key: str) -> ObjectHead:
        result = self._internal.head_object(Bucket=self._bucket, Key=object_key)
        return ObjectHead(
            content_type=str(result.get("ContentType", "")),
            size_bytes=int(result["ContentLength"]),
        )

    def get_bytes(self, *, object_key: str) -> bytes:
        result = self._internal.get_object(Bucket=self._bucket, Key=object_key)
        return bytes(result["Body"].read())

    def put_bytes(self, *, object_key: str, content_type: str, data: bytes) -> None:
        self._internal.put_object(
            Bucket=self._bucket, Key=object_key, Body=data, ContentType=content_type
        )

    def delete_objects(self, *, object_keys: Sequence[str]) -> None:
        for object_key in object_keys:
            self._internal.delete_object(Bucket=self._bucket, Key=object_key)
