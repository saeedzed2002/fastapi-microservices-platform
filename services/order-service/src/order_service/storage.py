from dataclasses import dataclass

import boto3  # type: ignore[import-untyped]
from botocore.client import Config  # type: ignore[import-untyped]

from order_service.config import Settings


@dataclass(frozen=True)
class ObjectHead:
    content_type: str
    size_bytes: int


class S3ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        options = {
            "aws_access_key_id": settings.s3_access_key_id,
            "aws_secret_access_key": settings.s3_secret_access_key,
            "region_name": settings.s3_region,
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        }
        self._bucket = settings.s3_bucket
        self._client = boto3.client("s3", endpoint_url=settings.s3_endpoint_url, **options)

    def ensure_bucket(self) -> None:
        names = {item["Name"] for item in self._client.list_buckets()["Buckets"]}
        if self._bucket not in names:
            self._client.create_bucket(Bucket=self._bucket)

    def put_bytes(self, *, object_key: str, content_type: str, data: bytes) -> None:
        self._client.put_object(
            Bucket=self._bucket, Key=object_key, Body=data, ContentType=content_type
        )

    def head(self, *, object_key: str) -> ObjectHead:
        result = self._client.head_object(Bucket=self._bucket, Key=object_key)
        return ObjectHead(
            content_type=str(result.get("ContentType", "")), size_bytes=int(result["ContentLength"])
        )
