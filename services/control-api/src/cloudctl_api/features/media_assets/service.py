"""F10 media-assets delta: deterministic derivatives, pool freeze, and preflight."""

from __future__ import annotations

import asyncio
import hashlib
import io
from datetime import UTC, datetime
from typing import Any

from cloudctl_domain import (
    Actor,
    ConflictError,
    NotFoundError,
    Permission,
    ValidationError,
    canonical_hash,
    require_permissions,
)
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from sqlalchemy import select

from ...db import (
    AccountDeviceBindingRow,
    AuditEventRow,
    DeviceRow,
    MediaAssetRow,
    MediaDerivativeRow,
    MediaGroupMembershipRow,
    MediaGroupRow,
    PlatformAccountRow,
    ProductMediaRow,
    ProductRow,
)
from ...media_store import ObjectStore
from ...repository import ControlRepository
from .schemas import MediaPoolFreezeRequest, PublishPreflightRequest, WatermarkRenderRequest

_MAX_IMAGE_PIXELS = 40_000_000
_PLATFORM_LIMITS = {"xianyu": 49, "xiaohongshu": 18}
_PLATFORM_PACKAGES = {
    "xianyu": "com.taobao.idlefish",
    "xiaohongshu": "com.xingin.xhs",
}
_FORBIDDEN_WORDS = (
    ("微信", "BLOCKED", "引流联系方式"),
    ("加微", "BLOCKED", "引流联系方式"),
    ("QQ", "BLOCKED", "引流联系方式"),
    ("站外交易", "BLOCKED", "站外交易"),
    ("刀具", "BLOCKED", "管制刀具"),
    ("毒品", "BLOCKED", "毒品"),
    ("国家级", "WARNING", "虚假主张"),
    ("最高级", "WARNING", "虚假主张"),
    ("全网最低", "WARNING", "虚假主张"),
    ("销量第一", "WARNING", "虚假主张"),
    ("国家免检", "WARNING", "虚假主张"),
    ("治疗", "WARNING", "疾病治疗宣称"),
    ("高仿", "WARNING", "高仿假货"),
    ("中奖", "WARNING", "诱导中奖"),
)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _check(check_id: str, category: str, status: str, detail: str) -> dict[str, str]:
    return {"id": check_id, "category": category, "status": status, "detail": detail}


class MediaAssetsService:
    def __init__(self, database: Any, object_store: ObjectStore) -> None:
        self.database = database
        self.object_store = object_store

    async def render_watermark(
        self, actor: Actor, source_asset_id: str, request: WatermarkRenderRequest
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        tenant_id = str(actor.tenant_id)
        async with self.database.unit_of_work() as session:
            source = await session.scalar(
                select(MediaAssetRow).where(
                    MediaAssetRow.id == source_asset_id,
                    MediaAssetRow.tenant_id == tenant_id,
                )
            )
            if source is None:
                raise NotFoundError("media asset was not found")
            if not source.content_type.lower().startswith("image/"):
                raise ValidationError("watermark source must be an image asset")
            object_key = source.object_key

        stored = await self.object_store.get(object_key)
        if stored is None:
            raise NotFoundError("media object was not found")
        output, width, height = await asyncio.to_thread(
            self._render, stored.content, request
        )
        output_sha256 = hashlib.sha256(output).hexdigest()
        output_key = f"tenants/{tenant_id}/media/derivatives/{output_sha256}.png"
        await asyncio.to_thread(
            self.object_store.put, output_key, output, "image/png"
        )

        profile = {
            "kind": "watermark",
            "text": request.text,
            "position": request.position,
            "opacity": request.opacity,
            "fontSize": request.font_size,
            "margin": request.margin,
            "ruleVersionId": request.rule_version_id,
        }
        profile_sha256 = canonical_hash(profile)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            existing = await repository.media_by_hash(output_sha256)
            if existing is not None and existing.source_asset_id != source_asset_id:
                raise ConflictError("derived media digest is already bound to another source")
            output_asset = existing
            if output_asset is None:
                output_asset = MediaAssetRow(
                    id=repository.new_id(),
                    tenant_id=repository.tenant_id,
                    sha256=output_sha256,
                    object_key=output_key,
                    content_type="image/png",
                    size_bytes=len(output),
                    source_asset_id=source_asset_id,
                    metadata_json={
                        "derivativeKind": "watermark",
                        "profile": profile,
                        "profileSha256": profile_sha256,
                        "width": width,
                        "height": height,
                    },
                    created_at=_now(),
                )
                repository.add(output_asset)
            derivative = MediaDerivativeRow(
                id=repository.new_id(),
                tenant_id=repository.tenant_id,
                source_asset_id=source_asset_id,
                profile_id=f"watermark:{profile_sha256}",
                state="SUCCEEDED",
                output_asset_id=output_asset.id,
                error_code=None,
                detail=None,
                completed_at=_now(),
                created_at=_now(),
            )
            repository.add(derivative)
            repository.audit(
                action="media.watermark.rendered",
                resource_type="media_derivative",
                resource_id=derivative.id,
                after={
                    "sourceAssetId": source_asset_id,
                    "outputAssetId": output_asset.id,
                    "sha256": output_sha256,
                    "profileSha256": profile_sha256,
                },
            )
            return {
                "derivativeId": derivative.id,
                "sourceAssetId": source_asset_id,
                "outputAsset": self._asset_view(output_asset),
                "profile": profile,
                "profileSha256": profile_sha256,
                "previewSha256": output_sha256,
                "publishDerivativeSha256": output_sha256,
            }

    async def freeze_pool(
        self, actor: Actor, request: MediaPoolFreezeRequest
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        tenant_id = str(actor.tenant_id)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            existing = await session.scalar(
                select(AuditEventRow)
                .where(
                    AuditEventRow.tenant_id == tenant_id,
                    AuditEventRow.action == "media.pool.frozen",
                    AuditEventRow.resource_id == request.task_key,
                )
                .order_by(AuditEventRow.occurred_at.asc())
            )
            if existing is not None:
                frozen = existing.metadata_json
                if (
                    frozen.get("groupId") != request.group_id
                    or frozen.get("count") != request.count
                    or (request.seed is not None and frozen.get("seed") != request.seed)
                ):
                    raise ConflictError(
                        "taskKey is already bound to a different media pool request"
                    )
                return {**frozen, "replayed": True}

            group = await session.scalar(
                select(MediaGroupRow).where(
                    MediaGroupRow.id == request.group_id,
                    MediaGroupRow.tenant_id == tenant_id,
                )
            )
            if group is None:
                raise NotFoundError("media group was not found")
            member_ids = list(
                await session.scalars(
                    select(MediaGroupMembershipRow.media_asset_id)
                    .where(
                        MediaGroupMembershipRow.group_id == group.id,
                        MediaGroupMembershipRow.tenant_id == tenant_id,
                    )
                    .order_by(MediaGroupMembershipRow.media_asset_id)
                )
            )
            if len(member_ids) < request.count:
                raise ValidationError("media group does not contain enough assets")
            assets = list(
                await session.scalars(
                    select(MediaAssetRow).where(
                        MediaAssetRow.tenant_id == tenant_id,
                        MediaAssetRow.id.in_(member_ids),
                    )
                )
            )
            if len(assets) != len(member_ids):
                raise ValidationError("media group contains missing assets")
            if any(not asset.content_type.lower().startswith("image/") for asset in assets):
                raise ValidationError("media pool may only freeze image assets")

            seed = request.seed or canonical_hash(
                {"tenantId": tenant_id, "taskKey": request.task_key, "groupId": group.id}
            )
            ordered = sorted(
                member_ids,
                key=lambda asset_id: hashlib.sha256(
                    f"{seed}\0{asset_id}".encode()
                ).digest(),
            )
            selected = ordered[: request.count]
            snapshot = {
                "taskKey": request.task_key,
                "groupId": group.id,
                "seed": seed,
                "count": request.count,
                "mediaAssetIds": selected,
            }
            frozen = {**snapshot, "snapshotSha256": canonical_hash(snapshot)}
            repository.audit(
                action="media.pool.frozen",
                resource_type="media_pool_snapshot",
                resource_id=request.task_key,
                after=frozen,
                metadata=frozen,
            )
            return {**frozen, "replayed": False}

    async def preflight(
        self, actor: Actor, request: PublishPreflightRequest
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.PUBLISH_CREATE)
        tenant_id = str(actor.tenant_id)
        checks: list[dict[str, str]] = []
        async with self.database.unit_of_work() as session:
            product = await session.scalar(
                select(ProductRow).where(
                    ProductRow.id == request.product_id,
                    ProductRow.tenant_id == tenant_id,
                )
            )
            if product is None:
                raise NotFoundError("product was not found")
            media_links = list(
                await session.scalars(
                    select(ProductMediaRow)
                    .where(
                        ProductMediaRow.product_id == product.id,
                        ProductMediaRow.tenant_id == tenant_id,
                    )
                    .order_by(ProductMediaRow.sort_order)
                )
            )
            media_ids = [item.media_asset_id for item in media_links]
            media_rows = list(
                await session.scalars(
                    select(MediaAssetRow).where(
                        MediaAssetRow.tenant_id == tenant_id,
                        MediaAssetRow.id.in_(media_ids),
                    )
                )
            ) if media_ids else []
            account = await session.scalar(
                select(PlatformAccountRow).where(
                    PlatformAccountRow.id == request.account_id,
                    PlatformAccountRow.tenant_id == tenant_id,
                )
            )
            device = await session.scalar(
                select(DeviceRow).where(
                    DeviceRow.id == request.device_id,
                    DeviceRow.tenant_id == tenant_id,
                )
            )
            binding = await session.scalar(
                select(AccountDeviceBindingRow).where(
                    AccountDeviceBindingRow.tenant_id == tenant_id,
                    AccountDeviceBindingRow.account_id == request.account_id,
                    AccountDeviceBindingRow.device_id == request.device_id,
                    AccountDeviceBindingRow.status == "BOUND",
                )
            )

            checks.append(
                _check(
                    "product.active",
                    "fields",
                    "PASS" if product.status == "ACTIVE" else "BLOCKED",
                    f"product status is {product.status}",
                )
            )
            for word, status, reason in _FORBIDDEN_WORDS:
                if word in f"{product.title}\n{product.description}":
                    checks.append(
                        _check(f"content.word.{word}", "content", status, f"{word}: {reason}")
                    )
            if not any(item["category"] == "content" for item in checks):
                checks.append(_check("content.words", "content", "PASS", "no policy words matched"))

            limit = _PLATFORM_LIMITS[request.platform]
            media_ok = (
                bool(media_ids)
                and len(media_ids) <= limit
                and len(media_rows) == len(media_ids)
                and all(row.content_type.lower().startswith("image/") for row in media_rows)
            )
            checks.append(
                _check(
                    "media.assets",
                    "media",
                    "PASS" if media_ok else "BLOCKED",
                    f"{len(media_ids)} ordered assets; platform limit is {limit}",
                )
            )
            account_ok = (
                account is not None
                and account.platform == request.platform
                and account.status == "AUTHORIZED"
                and (account.expires_at is None or _aware(account.expires_at) > _now())
            )
            checks.append(
                _check(
                    "account.authorization",
                    "account",
                    "PASS" if account_ok else "BLOCKED",
                    "account authorization is active and platform-matched"
                    if account_ok
                    else "account is missing, expired, unauthorized, or platform-mismatched",
                )
            )
            checks.append(
                _check(
                    "account.binding",
                    "account",
                    "PASS" if binding is not None else "BLOCKED",
                    "account is bound to the selected device"
                    if binding is not None
                    else "account is not bound to the selected device",
                )
            )
            device_ok = device is not None and not device.maintenance and device.state == "ONLINE"
            checks.append(
                _check(
                    "device.online",
                    "device",
                    "PASS" if device_ok else "BLOCKED",
                    "device is online and available"
                    if device_ok
                    else "device is missing, offline, or in maintenance",
                )
            )
            capabilities = device.capabilities if device is not None else {}
            accessibility_ok = capabilities.get("accessibilityEnabled") is True
            checks.append(
                _check(
                    "device.accessibility",
                    "device",
                    "PASS" if accessibility_ok else "BLOCKED",
                    "accessibility executor is enabled"
                    if accessibility_ok
                    else "accessibility executor is not confirmed enabled",
                )
            )
            package = _PLATFORM_PACKAGES[request.platform]
            app_version = (
                (device.target_app_versions or {}).get(package)
                if device is not None
                else None
            )
            checks.append(
                _check(
                    "device.target_app",
                    "device",
                    "PASS" if app_version else "BLOCKED",
                    f"target app version is {app_version}"
                    if app_version
                    else f"target app {package} version is not reported",
                )
            )

        snapshot = {
            "productId": product.id,
            "productRevision": product.revision,
            "mediaAssetIds": media_ids,
            "accountId": request.account_id,
            "bindingVersion": binding.binding_version if binding is not None else None,
            "deviceId": request.device_id,
            "platform": request.platform,
        }
        return {
            "ready": not any(item["status"] == "BLOCKED" for item in checks),
            "checks": checks,
            "snapshot": snapshot,
            "snapshotSha256": canonical_hash(snapshot),
        }

    @staticmethod
    def _render(content: bytes, request: WatermarkRenderRequest) -> tuple[bytes, int, int]:
        try:
            with Image.open(io.BytesIO(content)) as opened:
                image = ImageOps.exif_transpose(opened)
                image.load()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValidationError("source object is not a valid image") from exc
        width, height = image.size
        if width <= 0 or height <= 0 or width * height > _MAX_IMAGE_PIXELS:
            raise ValidationError("source image dimensions exceed the derivative limit")
        canvas = image.convert("RGBA")
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        font = ImageFont.load_default(size=request.font_size)
        stroke = max(1, request.font_size // 16)
        box = draw.textbbox((0, 0), request.text, font=font, stroke_width=stroke)
        text_width = box[2] - box[0]
        text_height = box[3] - box[1]
        positions = {
            "top_left": (request.margin, request.margin),
            "top_right": (width - text_width - request.margin, request.margin),
            "center": ((width - text_width) // 2, (height - text_height) // 2),
            "bottom_left": (request.margin, height - text_height - request.margin),
            "bottom_right": (
                width - text_width - request.margin,
                height - text_height - request.margin,
            ),
        }
        x, y = positions[request.position]
        if x < 0 or y < 0 or x + text_width > width or y + text_height > height:
            raise ValidationError("watermark text does not fit inside the source image")
        alpha = round(255 * request.opacity / 100)
        draw.text(
            (x, y),
            request.text,
            font=font,
            fill=(255, 255, 255, alpha),
            stroke_width=stroke,
            stroke_fill=(0, 0, 0, alpha),
        )
        output = Image.alpha_composite(canvas, overlay).convert("RGB")
        buffer = io.BytesIO()
        output.save(buffer, format="PNG", optimize=False, compress_level=9)
        return buffer.getvalue(), width, height

    @staticmethod
    def _asset_view(row: MediaAssetRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "sha256": row.sha256,
            "objectKey": row.object_key,
            "contentType": row.content_type,
            "sizeBytes": row.size_bytes,
            "sourceAssetId": row.source_asset_id,
            "metadata": row.metadata_json,
        }
