"""Source connector service for product and media library synchronization."""

from __future__ import annotations

import csv
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .source_schemas import (
    SourceConnectionConfig,
    SourcePreviewResponse,
    SourceRecordPreview,
)

logger = logging.getLogger(__name__)


class SourceConnector(ABC):
    """Base protocol for source connectors."""

    def __init__(self, config: SourceConnectionConfig, secret: dict[str, Any] | None = None):
        self.config = config
        self.secret = secret or {}

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str]:
        """Test connectivity and credentials. Returns (success, message)."""
        pass

    @abstractmethod
    async def read_page(
        self, cursor: str | None, page_size: int = 100
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Read one page of records. Returns (records, next_cursor)."""
        pass

    @abstractmethod
    async def fetch_asset(self, asset_ref: str) -> tuple[bytes, str]:
        """Fetch binary asset content. Returns (data, content_type)."""
        pass

    @abstractmethod
    def normalize_record(self, raw_record: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """
        Normalize external record to internal schema.
        Returns (normalized_data, errors).
        """
        pass

    def get_external_id(self, record: dict[str, Any]) -> str:
        """Extract stable external ID from record."""
        # Override in subclass if needed
        return str(record.get("id", ""))


class CSVFileConnector(SourceConnector):
    """Connector for local CSV files."""

    def __init__(self, config: dict[str, Any], secret: dict[str, Any] | None = None):
        self.base_path = Path(config.get("base_path", ""))
        self.file_name = config.get("file_name", "")
        self.encoding = config.get("encoding", "utf-8")
        self.entity_kind = config.get("entity_kind", "product")
        self._file_path = self.base_path / self.file_name
        super().__init__(config, secret)  # type: ignore[arg-type]

    async def test_connection(self) -> tuple[bool, str]:
        """Test that CSV file exists and is readable."""
        try:
            if not self._file_path.exists():
                return False, f"File not found: {self._file_path}"

            if not self._file_path.is_file():
                return False, f"Not a file: {self._file_path}"

            # Try reading header
            with open(self._file_path, encoding=self.encoding) as f:  # noqa: ASYNC230
                reader = csv.DictReader(f)
                _ = reader.fieldnames

            return True, f"CSV file accessible with {len(reader.fieldnames or [])} columns"
        except Exception as e:
            return False, f"Failed to read CSV: {e}"

    async def read_page(
        self, cursor: str | None, page_size: int = 100
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Read CSV records. Cursor is line offset."""
        records: list[dict[str, Any]] = []
        start_line = int(cursor) if cursor else 0

        try:
            with open(self._file_path, encoding=self.encoding) as f:  # noqa: ASYNC230
                reader = csv.DictReader(f)

                # Skip to cursor position
                for _ in range(start_line):
                    next(reader, None)

                # Read page
                for i, row in enumerate(reader):
                    if i >= page_size:
                        break
                    records.append(dict(row))

                # Next cursor
                if len(records) == page_size:
                    next_cursor = str(start_line + len(records))
                else:
                    next_cursor = None

                return records, next_cursor

        except Exception as e:
            logger.error(f"Failed to read CSV page: {e}")
            return [], None

    async def fetch_asset(self, asset_ref: str) -> tuple[bytes, str]:
        """Fetch media file from local filesystem."""
        # asset_ref is relative path from media folder
        media_folder = self.base_path / "media"
        asset_path = media_folder / asset_ref

        if not asset_path.exists():
            msg = f"Asset not found: {asset_ref}"
            raise FileNotFoundError(msg)

        # Determine content type from extension
        suffix = asset_path.suffix.lower()
        content_type_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".mp4": "video/mp4",
        }
        content_type = content_type_map.get(suffix, "application/octet-stream")

        with open(asset_path, "rb") as f:  # noqa: ASYNC230
            data = f.read()

        return data, content_type

    def normalize_record(self, raw_record: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """Normalize CSV record to internal Product/Media schema."""
        errors: list[str] = []

        if self.entity_kind == "product":
            return self._normalize_product(raw_record, errors)
        elif self.entity_kind == "media":
            return self._normalize_media(raw_record, errors)
        else:
            errors.append(f"Unknown entity_kind: {self.entity_kind}")
            return {}, errors

    def _normalize_product(
        self, raw: dict[str, Any], errors: list[str]
    ) -> tuple[dict[str, Any], list[str]]:
        """Normalize product record."""
        normalized: dict[str, Any] = {}

        # Required fields
        if not raw.get("product_id"):
            errors.append("Missing required field: product_id")
        else:
            normalized["spu_code"] = raw["product_id"]

        if not raw.get("title"):
            errors.append("Missing required field: title")
        else:
            title = raw["title"]
            if len(title) > 255:
                errors.append(f"Title exceeds 255 chars: {len(title)}")
            normalized["title"] = title[:255]

        if not raw.get("description"):
            errors.append("Missing required field: description")
        else:
            normalized["description"] = raw["description"]

        if not raw.get("price"):
            errors.append("Missing required field: price")
        else:
            try:
                # Convert to string decimal format
                normalized["price"] = str(float(raw["price"]))
            except ValueError:
                errors.append(f"Invalid price format: {raw['price']}")

        # Optional fields
        normalized["stock"] = int(raw.get("stock", 0))
        normalized["category"] = raw.get("category", "")
        normalized["status"] = "ACTIVE"

        # Parse media references (semicolon-separated)
        media_refs = raw.get("media_refs", "")
        if media_refs:
            normalized["media_refs"] = [ref.strip() for ref in media_refs.split(";") if ref.strip()]
        else:
            normalized["media_refs"] = []

        # Version tracking
        if raw.get("updated_at"):
            normalized["updated_at"] = raw["updated_at"]

        return normalized, errors

    def _normalize_media(
        self, raw: dict[str, Any], errors: list[str]
    ) -> tuple[dict[str, Any], list[str]]:
        """Normalize media record."""
        normalized: dict[str, Any] = {}

        # Required fields
        if not raw.get("file_name"):
            errors.append("Missing required field: file_name")
        else:
            normalized["file_name"] = raw["file_name"]

        if not raw.get("sha256"):
            errors.append("Missing required field: sha256")
        else:
            sha256 = raw["sha256"]
            if len(sha256) != 64:
                errors.append(f"Invalid SHA256 length: {len(sha256)}, expected 64")
            normalized["sha256"] = sha256

        if not raw.get("content_type"):
            errors.append("Missing required field: content_type")
        else:
            normalized["content_type"] = raw["content_type"]

        if not raw.get("size_bytes"):
            errors.append("Missing required field: size_bytes")
        else:
            try:
                normalized["size_bytes"] = int(raw["size_bytes"])
            except ValueError:
                errors.append(f"Invalid size_bytes: {raw['size_bytes']}")

        # Optional fields
        if raw.get("width"):
            try:
                normalized["width"] = int(raw["width"])
            except ValueError:
                pass

        if raw.get("height"):
            try:
                normalized["height"] = int(raw["height"])
            except ValueError:
                pass

        normalized["file_path"] = raw.get("file_path", raw.get("file_name", ""))

        return normalized, errors

    def get_external_id(self, record: dict[str, Any]) -> str:
        """Extract external ID based on entity kind."""
        if self.entity_kind == "product":
            value = record.get("product_id", "")
            return value if isinstance(value, str) else ""
        if self.entity_kind == "media":
            value = record.get("file_name", "")
            return value if isinstance(value, str) else ""
        return ""


def create_connector(
    source_kind: str, config: dict[str, Any], secret: dict[str, Any] | None = None
) -> SourceConnector:
    """Factory to create appropriate connector instance."""
    if source_kind == "csv_file":
        return CSVFileConnector(config, secret)
    else:
        msg = f"Unsupported source_kind: {source_kind}"
        raise ValueError(msg)


async def preview_source(
    source_kind: str,
    config: dict[str, Any],
    secret: dict[str, Any] | None = None,
    page_size: int = 10,
) -> SourcePreviewResponse:
    """Preview records from a source without writing to database."""
    connector = create_connector(source_kind, config, secret)

    # Test connection first
    success, message = await connector.test_connection()
    if not success:
        return SourcePreviewResponse(
            total_read=0,
            valid_records=0,
            invalid_records=1,
            records=[
                SourceRecordPreview(
                    external_id="connection_test",
                    raw_data={},
                    errors=[f"Connection test failed: {message}"],
                )
            ],
        )

    # Read one page
    raw_records, next_cursor = await connector.read_page(cursor=None, page_size=page_size)

    previews: list[SourceRecordPreview] = []
    valid_count = 0
    invalid_count = 0

    for raw in raw_records:
        external_id = connector.get_external_id(raw)
        normalized, errors = connector.normalize_record(raw)

        preview = SourceRecordPreview(
            external_id=external_id,
            raw_data=raw,
            normalized_data=normalized if not errors else None,
            errors=errors,
        )
        previews.append(preview)

        if errors:
            invalid_count += 1
        else:
            valid_count += 1

    return SourcePreviewResponse(
        total_read=len(raw_records),
        valid_records=valid_count,
        invalid_records=invalid_count,
        records=previews,
        cursor=next_cursor,
    )


async def execute_sync_run(
    session: Any,
    connection_id: str,
    tenant_id: str,
    triggered_by: str,
    connector: SourceConnector,
    object_store: Any,
    run_mode: str = "incremental",
    page_size: int = 100,
) -> dict[str, Any]:
    """
    Execute a synchronization run.

    Returns summary dict with counts and status.
    """
    from datetime import UTC, datetime
    from uuid import uuid4

    from sqlalchemy import select

    from .db import (
        SourceConnectionRow,
        SourceRecordLinkRow,
        SyncRunRow,
    )

    # Create sync run record
    sync_run_id = str(uuid4())
    now = datetime.now(UTC)

    # Get cursor from last successful run
    stmt = (
        select(SyncRunRow)
        .where(
            SyncRunRow.tenant_id == tenant_id,
            SyncRunRow.connection_id == connection_id,
            SyncRunRow.status == "completed",
        )
        .order_by(SyncRunRow.completed_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    last_run = result.scalar_one_or_none()
    cursor_before = last_run.cursor_after if last_run and run_mode == "incremental" else None

    sync_run = SyncRunRow(
        id=sync_run_id,
        tenant_id=tenant_id,
        connection_id=connection_id,
        run_mode=run_mode,
        status="running",
        started_at=now,
        cursor_before=cursor_before,
        cursor_after=None,
        records_read=0,
        records_created=0,
        records_updated=0,
        records_failed=0,
        triggered_by=triggered_by,
        created_at=now,
    )
    session.add(sync_run)
    await session.flush()

    # Get connection config
    conn_stmt = select(SourceConnectionRow).where(SourceConnectionRow.id == connection_id)
    conn_result = await session.execute(conn_stmt)
    connection = conn_result.scalar_one()
    entity_kind = connection.entity_kind

    # Sync pages
    current_cursor = cursor_before
    total_read = 0
    total_created = 0
    total_updated = 0
    total_failed = 0

    try:
        while True:
            # Read page
            raw_records, next_cursor = await connector.read_page(
                cursor=current_cursor, page_size=page_size
            )

            if not raw_records:
                break

            # Process each record
            for raw in raw_records:
                total_read += 1
                external_id = connector.get_external_id(raw)

                try:
                    # Normalize
                    normalized, errors = connector.normalize_record(raw)

                    if errors:
                        # Record error
                        await _record_sync_error(
                            session,
                            sync_run_id,
                            connection_id,
                            tenant_id,
                            external_id,
                            errors,
                            raw,
                        )
                        total_failed += 1
                        continue

                    # Compute record hash
                    import hashlib
                    import json

                    record_json = json.dumps(normalized, sort_keys=True)
                    record_hash = hashlib.sha256(record_json.encode()).hexdigest()

                    # Check existing link
                    link_stmt = select(SourceRecordLinkRow).where(
                        SourceRecordLinkRow.tenant_id == tenant_id,
                        SourceRecordLinkRow.connection_id == connection_id,
                        SourceRecordLinkRow.external_id == external_id,
                    )
                    link_result = await session.execute(link_stmt)
                    existing_link = link_result.scalar_one_or_none()

                    if existing_link and existing_link.record_hash == record_hash:
                        # Same hash, skip
                        continue

                    # Create or update entity
                    if entity_kind == "product":
                        entity_id = await _sync_product(
                            session, tenant_id, normalized, existing_link, object_store, connector
                        )
                        if existing_link:
                            total_updated += 1
                        else:
                            total_created += 1
                    elif entity_kind == "media":
                        entity_id = await _sync_media(
                            session, tenant_id, normalized, existing_link, object_store, connector
                        )
                        if existing_link:
                            total_updated += 1
                        else:
                            total_created += 1
                    else:
                        raise ValueError(f"Unknown entity_kind: {entity_kind}")

                    # Update or create link
                    if existing_link:
                        existing_link.record_hash = record_hash
                        existing_link.last_synced_at = now
                        existing_link.entity_id = entity_id
                    else:
                        link = SourceRecordLinkRow(
                            id=str(uuid4()),
                            tenant_id=tenant_id,
                            connection_id=connection_id,
                            external_id=external_id,
                            entity_kind=entity_kind,
                            entity_id=entity_id,
                            record_hash=record_hash,
                            last_synced_at=now,
                            created_at=now,
                        )
                        session.add(link)

                except Exception as e:
                    # Record error
                    await _record_sync_error(
                        session,
                        sync_run_id,
                        connection_id,
                        tenant_id,
                        external_id,
                        [str(e)],
                        raw,
                    )
                    total_failed += 1

            # Commit page
            sync_run.cursor_after = next_cursor
            sync_run.records_read = total_read
            sync_run.records_created = total_created
            sync_run.records_updated = total_updated
            sync_run.records_failed = total_failed
            await session.flush()

            # Move to next page
            current_cursor = next_cursor
            if not next_cursor:
                break

        # Mark completed
        sync_run.status = "completed"
        sync_run.completed_at = datetime.now(UTC)
        await session.flush()

        return {
            "sync_run_id": sync_run_id,
            "status": "completed",
            "records_read": total_read,
            "records_created": total_created,
            "records_updated": total_updated,
            "records_failed": total_failed,
        }

    except Exception as e:
        sync_run.status = "failed"
        sync_run.error_summary = str(e)
        sync_run.completed_at = datetime.now(UTC)
        await session.flush()
        raise


async def _record_sync_error(
    session: Any,
    sync_run_id: str,
    connection_id: str,
    tenant_id: str,
    external_id: str,
    errors: list[str],
    raw_record: dict[str, Any],
) -> None:
    """Record synchronization error."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from .db import SyncErrorRow

    for error_msg in errors:
        error = SyncErrorRow(
            id=str(uuid4()),
            tenant_id=tenant_id,
            sync_run_id=sync_run_id,
            connection_id=connection_id,
            external_id=external_id,
            error_code="VALIDATION_ERROR",
            error_message=error_msg,
            field_name=None,
            record_snapshot=raw_record,
            retry_count=0,
            created_at=datetime.now(UTC),
        )
        session.add(error)


async def _sync_product(
    session: Any,
    tenant_id: str,
    normalized: dict[str, Any],
    existing_link: Any,
    object_store: Any,
    connector: SourceConnector,
) -> str:
    """Sync product entity."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from sqlalchemy import select

    from .db import MediaAssetRow, ProductMediaRow, ProductRow

    if existing_link and existing_link.entity_id:
        # Update existing product
        stmt = select(ProductRow).where(ProductRow.id == existing_link.entity_id)
        result = await session.execute(stmt)
        product = result.scalar_one()

        product.title = normalized["title"]
        product.description = normalized["description"]
        product.price = normalized["price"]
        product.stock = normalized.get("stock", 0)
        product.category = normalized.get("category", "")
        product.revision += 1

        entity_id = str(product.id)
    else:
        # Create new product
        entity_id = str(uuid4())
        product = ProductRow(
            id=entity_id,
            tenant_id=tenant_id,
            spu_code=normalized["spu_code"],
            title=normalized["title"],
            description=normalized["description"],
            category=normalized.get("category", ""),
            price=normalized["price"],
            stock=normalized.get("stock", 0),
            status=normalized.get("status", "ACTIVE"),
            revision=1,
            attributes={},
            created_at=datetime.now(UTC),
        )
        session.add(product)

    # Handle media references
    media_refs = normalized.get("media_refs", [])
    if media_refs:
        # Remove old media associations
        from sqlalchemy import delete

        del_stmt = delete(ProductMediaRow).where(ProductMediaRow.product_id == entity_id)
        await session.execute(del_stmt)

        # Add new media associations
        for i, media_ref in enumerate(media_refs):
            # Find media asset by file name (stored in metadata_json)
            # For SQLite compatibility, we fetch all assets and filter in Python
            media_stmt = select(MediaAssetRow).where(
                MediaAssetRow.tenant_id == tenant_id,
            )
            media_result = await session.execute(media_stmt)
            all_media = media_result.scalars().all()

            # Filter by file_name in metadata
            media_asset = None
            for asset in all_media:
                if asset.metadata_json.get("file_name") == media_ref:
                    media_asset = asset
                    break

            if media_asset:
                pm = ProductMediaRow(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    product_id=entity_id,
                    media_asset_id=media_asset.id,
                    sort_order=i,
                    role="cover" if i == 0 else "gallery",
                    created_at=datetime.now(UTC),
                )
                session.add(pm)

    return entity_id


async def _sync_media(
    session: Any,
    tenant_id: str,
    normalized: dict[str, Any],
    existing_link: Any,
    object_store: Any,
    connector: SourceConnector,
) -> str:
    """Sync media entity with asset download."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from sqlalchemy import select

    from .db import MediaAssetRow

    sha256 = normalized["sha256"]

    # Check if asset already exists by SHA256
    stmt = select(MediaAssetRow).where(
        MediaAssetRow.tenant_id == tenant_id,
        MediaAssetRow.sha256 == sha256,
    )
    result = await session.execute(stmt)
    existing_asset = result.scalar_one_or_none()

    if existing_asset:
        # Asset already exists, update metadata
        existing_asset.metadata_json = {
            "file_name": normalized["file_name"],
            "width": normalized.get("width"),
            "height": normalized.get("height"),
        }
        return str(existing_asset.id)

    # Download and verify asset
    file_name = normalized["file_name"]
    try:
        asset_data, content_type = await connector.fetch_asset(file_name)

        # Verify SHA256
        import hashlib

        actual_sha256 = hashlib.sha256(asset_data).hexdigest()
        if actual_sha256 != sha256:
            msg = f"SHA256 mismatch for {file_name}: expected {sha256}, got {actual_sha256}"
            raise ValueError(msg)

    except FileNotFoundError as e:
        # Asset file not available, skip this media item
        msg = f"Media file not found: {file_name}"
        raise FileNotFoundError(msg) from e

    # Store in object store
    object_key = f"media/{tenant_id}/{sha256[:2]}/{sha256}"
    object_store.put(object_key, asset_data, content_type)

    # Create media asset
    entity_id = str(uuid4())
    asset = MediaAssetRow(
        id=entity_id,
        tenant_id=tenant_id,
        sha256=sha256,
        object_key=object_key,
        content_type=content_type,
        size_bytes=len(asset_data),
        metadata_json={
            "file_name": file_name,
            "width": normalized.get("width"),
            "height": normalized.get("height"),
        },
        created_at=datetime.now(UTC),
    )
    session.add(asset)

    return entity_id
