"""F11 content-io: dry-run/apply import, formula-safe export, immutable revisions.

The legacy ``/products:import`` surface keeps its frozen semantics; this
namespace adds the policy layer — validation without mutation by default,
explicit ``apply`` to write, row-precise outcomes, replay by import key,
append-only revision reads over the audit trail, and a CSV export that
neutralizes spreadsheet formula injection.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

from cloudctl_domain import (
    Actor,
    NotFoundError,
    Permission,
    canonical_hash,
    require_permissions,
)
from sqlalchemy import func, select

from ...db import AuditEventRow, ContentGroupMembershipRow, ContentGroupRow, ProductRow
from ...repository import ControlRepository
from .schemas import ContentImportRunRequest

_IMPORT_APPLIED_ACTION = "content_io.import.applied"
_ROW_IMPORT = "IMPORT"
_ROW_SKIP_EXISTING = "SKIP_EXISTING"
_ROW_ERROR = "ERROR"
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_EXPORT_COLUMNS = (
    "spuCode",
    "title",
    "description",
    "category",
    "price",
    "stock",
    "status",
    "revision",
    "createdAt",
)


def _now() -> datetime:
    return datetime.now(UTC)


class ContentIOService:
    def __init__(self, database: Any) -> None:
        self.database = database

    async def run_import(self, actor: Actor, request: ContentImportRunRequest) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_WRITE)
        tenant_id = str(actor.tenant_id)
        import_key = request.import_key or canonical_hash(
            {
                "items": [
                    {
                        "spuCode": item.spu_code,
                        "title": item.title,
                        "description": item.description,
                        "category": item.category,
                        "price": item.price,
                        "stock": item.stock,
                        "imageUrls": list(item.image_urls or []),
                        "groupId": item.group_id,
                    }
                    for item in request.items
                ],
                "groupId": request.group_id,
            }
        )

        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)

            replay = await session.scalar(
                select(AuditEventRow)
                .where(
                    AuditEventRow.tenant_id == tenant_id,
                    AuditEventRow.action == _IMPORT_APPLIED_ACTION,
                    AuditEventRow.resource_id == import_key,
                )
                .order_by(AuditEventRow.occurred_at.asc())
            )
            if replay is not None:
                stored = dict((replay.metadata_json or {}).get("result") or {})
                return {**stored, "importKey": import_key, "replayed": True}

            if request.group_id:
                group = await session.scalar(
                    select(ContentGroupRow).where(
                        ContentGroupRow.id == request.group_id,
                        ContentGroupRow.tenant_id == tenant_id,
                    )
                )
                if group is None:
                    raise NotFoundError("content group was not found")

            codes = [item.spu_code for item in request.items]
            existing_codes = set(
                await session.scalars(
                    select(ProductRow.spu_code).where(
                        ProductRow.tenant_id == tenant_id,
                        ProductRow.spu_code.in_(codes),
                    )
                )
            )

            rows: list[dict[str, Any]] = []
            positions: dict[str, list[int]] = {}
            for index, item in enumerate(request.items):
                positions.setdefault(item.spu_code, []).append(index)
            for index, item in enumerate(request.items):
                errors: list[dict[str, str]] = []
                occurrences = positions[item.spu_code]
                if len(occurrences) > 1:
                    errors.append(
                        {
                            "field": "spuCode",
                            "code": "DUPLICATE_IN_FILE",
                            "message": (
                                f"spuCode {item.spu_code} appears "
                                f"{len(occurrences)} times in this import "
                                f"(rows {occurrences})"
                            ),
                        }
                    )
                row_status = _ROW_IMPORT
                if item.spu_code in existing_codes:
                    row_status = _ROW_SKIP_EXISTING
                if errors:
                    row_status = _ROW_ERROR
                rows.append(
                    {
                        "index": index,
                        "spuCode": item.spu_code,
                        "title": item.title,
                        "status": row_status,
                        "errors": errors,
                    }
                )

            summary = {
                "total": len(rows),
                "importCount": sum(row["status"] == _ROW_IMPORT for row in rows),
                "skipExistingCount": sum(row["status"] == _ROW_SKIP_EXISTING for row in rows),
                "errorCount": sum(row["status"] == _ROW_ERROR for row in rows),
            }
            policy = (
                "apply=false：仅验证不写库；apply=true：合法行导入，"
                "已有 spuCode 跳过不覆盖，错误行精确报出并跳过。"
            )

            if not request.apply:
                return {
                    "mode": "DRY_RUN",
                    "apply": False,
                    "replayed": False,
                    "importKey": import_key,
                    "groupId": request.group_id,
                    "rows": rows,
                    "summary": summary,
                    "policy": policy,
                }

            for index, item in enumerate(request.items):
                if rows[index]["status"] != _ROW_IMPORT:
                    continue
                product_id = repository.new_id()
                repository.add(
                    ProductRow(
                        id=product_id,
                        tenant_id=tenant_id,
                        spu_code=item.spu_code,
                        title=item.title,
                        description=item.description,
                        category=item.category,
                        price=item.price,
                        stock=item.stock,
                        status="ACTIVE",
                        revision=1,
                        attributes={"imageUrls": list(item.image_urls or [])},
                        created_at=_now(),
                    )
                )
                group_id = item.group_id or request.group_id
                if group_id:
                    repository.add(
                        ContentGroupMembershipRow(
                            id=repository.new_id(),
                            tenant_id=tenant_id,
                            group_id=group_id,
                            content_id=product_id,
                            created_at=_now(),
                        )
                    )
                rows[index]["productId"] = product_id
                repository.audit(
                    action="product.imported",
                    resource_type="product",
                    resource_id=product_id,
                    after={
                        "revision": 1,
                        "spuCode": item.spu_code,
                        "title": item.title,
                    },
                    metadata={
                        "revision": 1,
                        "spuCode": item.spu_code,
                        "title": item.title,
                        "description": item.description,
                        "category": item.category,
                        "price": item.price,
                        "stock": item.stock,
                        "importKey": import_key,
                    },
                )

            result = {
                "mode": "APPLY",
                "apply": True,
                "replayed": False,
                "importKey": import_key,
                "groupId": request.group_id,
                "rows": rows,
                "summary": summary,
                "policy": policy,
            }
            repository.audit(
                action=_IMPORT_APPLIED_ACTION,
                resource_type="content_io_import",
                resource_id=import_key,
                after={"summary": summary},
                metadata={"result": result},
            )
            return result

    async def export_csv(
        self,
        actor: Actor,
        *,
        status_filter: str | None = None,
        category: str | None = None,
    ) -> tuple[str, str]:
        require_permissions(actor.roles, Permission.CONTENT_READ)
        tenant_id = str(actor.tenant_id)
        async with self.database.unit_of_work() as session:
            query = select(ProductRow).where(ProductRow.tenant_id == tenant_id)
            if status_filter:
                query = query.where(ProductRow.status == status_filter)
            if category:
                query = query.where(ProductRow.category == category)
            products = list(await session.scalars(query.order_by(ProductRow.spu_code.asc())))
            buffer = io.StringIO()
            writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
            writer.writerow(_EXPORT_COLUMNS)
            for product in products:
                writer.writerow(
                    [
                        self._csv_cell(product.spu_code),
                        self._csv_cell(product.title),
                        self._csv_cell((product.description or "").replace("\r", " ")),
                        self._csv_cell(product.category),
                        self._csv_cell(product.price),
                        self._csv_cell(product.stock),
                        self._csv_cell(product.status),
                        self._csv_cell(product.revision),
                        self._csv_cell(
                            product.created_at.isoformat() if product.created_at else ""
                        ),
                    ]
                )
        stamp = _now().strftime("%Y%m%d")
        return f"products-{stamp}.csv", buffer.getvalue()

    async def revisions(
        self,
        actor: Actor,
        product_id: str,
        *,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.CONTENT_READ)
        tenant_id = str(actor.tenant_id)
        async with self.database.unit_of_work() as session:
            product = await session.scalar(
                select(ProductRow).where(
                    ProductRow.id == product_id,
                    ProductRow.tenant_id == tenant_id,
                )
            )
            if product is None:
                raise NotFoundError("product was not found")
            conditions = (
                AuditEventRow.tenant_id == tenant_id,
                AuditEventRow.resource_type == "product",
                AuditEventRow.resource_id == product_id,
            )
            total = await session.scalar(
                select(func.count()).select_from(AuditEventRow).where(*conditions)
            )
            events = list(
                await session.scalars(
                    select(AuditEventRow)
                    .where(*conditions)
                    .order_by(AuditEventRow.occurred_at.desc(), AuditEventRow.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            items = [
                {
                    "eventId": event.id,
                    "revision": (event.metadata_json or {}).get("revision"),
                    "action": event.action,
                    "actorType": event.actor_type,
                    "actorId": event.actor_id,
                    "requestId": event.request_id,
                    "result": event.result,
                    "afterHash": event.after_hash,
                    "occurredAt": event.occurred_at.isoformat() if event.occurred_at else None,
                    "snapshot": event.metadata_json or {},
                }
                for event in events
            ]
            return {
                "productId": product_id,
                "currentRevision": product.revision,
                "total": int(total or 0),
                "limit": limit,
                "offset": offset,
                "items": items,
            }

    @staticmethod
    def _csv_cell(value: Any) -> str:
        text = "" if value is None else str(value)
        if text.startswith(_FORMULA_PREFIXES):
            return f"'{text}"
        return text
