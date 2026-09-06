"""Object-store ports for checksum-bound media uploads."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib
from dataclasses import dataclass
from typing import Any, Protocol, cast

from .settings import Settings


@dataclass(frozen=True, slots=True)
class UploadGrant:
    url: str
    headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class StoredObject:
    size_bytes: int
    sha256: str
    content_type: str


@dataclass(frozen=True, slots=True)
class DownloadedObject:
    content: bytes
    content_type: str


class ObjectStore(Protocol):
    async def create_upload(
        self,
        object_key: str,
        *,
        content_type: str,
        size_bytes: int,
        sha256: str,
        expires_seconds: int,
    ) -> UploadGrant: ...

    async def head(self, object_key: str) -> StoredObject | None: ...

    async def get(self, object_key: str) -> DownloadedObject | None: ...


class InMemoryObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def create_upload(
        self,
        object_key: str,
        *,
        content_type: str,
        size_bytes: int,
        sha256: str,
        expires_seconds: int,
    ) -> UploadGrant:
        del size_bytes, expires_seconds
        return UploadGrant(
            url=f"memory://uploads/{object_key}",
            headers={"Content-Type": content_type, "X-Checksum-SHA256": sha256},
        )

    async def head(self, object_key: str) -> StoredObject | None:
        value = self.objects.get(object_key)
        if value is None:
            return None
        content, content_type = value
        return StoredObject(
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            content_type=content_type,
        )

    async def get(self, object_key: str) -> DownloadedObject | None:
        value = self.objects.get(object_key)
        if value is None:
            return None
        content, content_type = value
        return DownloadedObject(content=content, content_type=content_type)

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        self.objects[object_key] = (content, content_type)


class S3ObjectStore:
    def __init__(self, settings: Settings) -> None:
        boto3 = importlib.import_module("boto3")
        access_key = settings.s3_access_key.get_secret_value() if settings.s3_access_key else None
        secret_key = settings.s3_secret_key.get_secret_value() if settings.s3_secret_key else None
        self.bucket = settings.s3_bucket
        self.client = cast(
            Any,
            boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint,
                region_name=settings.s3_region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
            ),
        )

    async def create_upload(
        self,
        object_key: str,
        *,
        content_type: str,
        size_bytes: int,
        sha256: str,
        expires_seconds: int,
    ) -> UploadGrant:
        del size_bytes
        checksum = base64.b64encode(bytes.fromhex(sha256)).decode("ascii")
        url = await asyncio.to_thread(
            self.client.generate_presigned_url,
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": object_key,
                "ContentType": content_type,
                "ChecksumSHA256": checksum,
            },
            ExpiresIn=expires_seconds,
            HttpMethod="PUT",
        )
        return UploadGrant(
            url=str(url),
            headers={"Content-Type": content_type, "X-Amz-Checksum-Sha256": checksum},
        )

    async def head(self, object_key: str) -> StoredObject | None:
        try:
            response = await asyncio.to_thread(
                self.client.head_object,
                Bucket=self.bucket,
                Key=object_key,
                ChecksumMode="ENABLED",
            )
        except self.client.exceptions.ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404:
                return None
            raise
        checksum = response.get("ChecksumSHA256")
        if not isinstance(checksum, str):
            return None
        return StoredObject(
            size_bytes=int(response["ContentLength"]),
            sha256=base64.b64decode(checksum).hex(),
            content_type=str(response.get("ContentType") or "application/octet-stream"),
        )

    async def get(self, object_key: str) -> DownloadedObject | None:
        try:
            response = await asyncio.to_thread(
                self.client.get_object,
                Bucket=self.bucket,
                Key=object_key,
            )
        except self.client.exceptions.ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404:
                return None
            raise
        body = response["Body"]
        content = await asyncio.to_thread(body.read)
        return DownloadedObject(
            content=bytes(content),
            content_type=str(response.get("ContentType") or "application/octet-stream"),
        )


def create_object_store(settings: Settings) -> ObjectStore:
    if settings.object_store_mode == "s3":
        return S3ObjectStore(settings)
    return InMemoryObjectStore()
