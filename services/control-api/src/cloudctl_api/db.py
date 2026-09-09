"""SQLAlchemy schema and explicit unit-of-work boundary."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from .settings import Settings


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantRow(Base, TimestampMixin):
    __tablename__ = "tenant"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)


class UserRow(Base, TimestampMixin):
    __tablename__ = "user_account"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), index=True)
    oidc_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    roles: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "oidc_subject"),)


class EdgeRow(Base, TimestampMixin):
    __tablename__ = "edge_node"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    logical_name: Mapped[str] = mapped_column(String(160), nullable=False)
    certificate_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("tenant_id", "logical_name"),)


class DeviceRow(Base, TimestampMixin):
    __tablename__ = "device"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    edge_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("edge_node.id"))
    logical_name: Mapped[str] = mapped_column(String(160), nullable=False)
    android_version: Mapped[str | None] = mapped_column(String(32))
    lamda_version: Mapped[str | None] = mapped_column(String(32))
    target_app_versions: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    labels: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    maintenance: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fencing_counter: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    control_epoch: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_binding_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (UniqueConstraint("tenant_id", "logical_name"),)


class PlatformAccountRow(Base, TimestampMixin):
    __tablename__ = "platform_account"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    external_subject_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    display_label: Mapped[str] = mapped_column(String(160), nullable=False)
    secret_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    authorization_basis: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "platform", "external_subject_ref"),)


class AccountDeviceBindingRow(Base, TimestampMixin):
    __tablename__ = "account_device_binding"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("platform_account.id"), index=True, nullable=False
    )
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("device.id"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    confirmed_by: Mapped[str] = mapped_column(String(36), nullable=False)
    confirmation_note: Mapped[str] = mapped_column(String(1000), nullable=False)
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    unbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    binding_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    platform: Mapped[str] = mapped_column(String(160), index=True, nullable=False, default="")
    __table_args__ = (
        UniqueConstraint("account_id", "device_id"),
        Index(
            "uq_account_device_binding_device_platform_bound",
            "device_id",
            "platform",
            unique=True,
            postgresql_where=text("status = 'BOUND'"),
            sqlite_where=text("status = 'BOUND'"),
        ),
    )


class TaskScheduleRow(Base, TimestampMixin):
    __tablename__ = "task_schedule"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    once_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rrule: Mapped[str | None] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    template_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    miss_policy: Mapped[str] = mapped_column(String(32), default="QUEUE_ONE", nullable=False)
    start_deadline_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    account_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    binding_version: Mapped[int] = mapped_column(Integer, nullable=False)
    device_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    command_type: Mapped[str] = mapped_column(String(80), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    paused_reason: Mapped[str | None] = mapped_column(String(160))
    last_error: Mapped[str | None] = mapped_column(Text)


class TaskScheduleFireRow(Base, TimestampMixin):
    __tablename__ = "task_schedule_fire"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    schedule_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("task_schedule.id"), index=True, nullable=False
    )
    device_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_for_local: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(36))
    detail: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("schedule_id", "scheduled_for", "device_id"),)


class MediaAssetRow(Base, TimestampMixin):
    __tablename__ = "media_asset"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    source_asset_id: Mapped[str | None] = mapped_column(String(36))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "sha256"),)


class MediaTagRow(Base, TimestampMixin):
    __tablename__ = "media_tag"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    media_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_asset.id"), index=True, nullable=False
    )
    tag: Mapped[str] = mapped_column(String(80), nullable=False)
    __table_args__ = (UniqueConstraint("media_asset_id", "tag"),)


class MediaGroupRow(Base, TimestampMixin):
    __tablename__ = "media_group"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)


class MediaGroupMembershipRow(Base, TimestampMixin):
    __tablename__ = "media_group_membership"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_group.id"), index=True, nullable=False
    )
    media_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_asset.id"), index=True, nullable=False
    )
    __table_args__ = (UniqueConstraint("group_id", "media_asset_id"),)


class ProductRow(Base, TimestampMixin):
    __tablename__ = "product"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    spu_code: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(160), nullable=False)
    price: Mapped[str] = mapped_column(String(32), nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "spu_code"),)


class ProductMediaRow(Base, TimestampMixin):
    __tablename__ = "product_media"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("product.id"), index=True, nullable=False
    )
    media_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_asset.id"), index=True, nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    __table_args__ = (UniqueConstraint("product_id", "media_asset_id"),)


class ProductGroupRow(Base, TimestampMixin):
    __tablename__ = "product_group"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)


class ProductGroupMembershipRow(Base, TimestampMixin):
    __tablename__ = "product_group_membership"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("product_group.id"), index=True, nullable=False
    )
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("product.id"), index=True, nullable=False
    )
    added_by: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (UniqueConstraint("group_id", "product_id"),)


class MediaUploadRow(Base, TimestampMixin):
    __tablename__ = "media_upload"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    expected_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    source_asset_id: Mapped[str | None] = mapped_column(String(36))
    derivative_profile_id: Mapped[str | None] = mapped_column(String(160))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    state: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MediaDerivativeRow(Base, TimestampMixin):
    __tablename__ = "media_derivative"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    source_asset_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(160), nullable=False)
    state: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    output_asset_id: Mapped[str | None] = mapped_column(String(36))
    error_code: Mapped[str | None] = mapped_column(String(80))
    detail: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContentItemRow(Base, TimestampMixin):
    __tablename__ = "content_item"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContentGroupRow(Base, TimestampMixin):
    __tablename__ = "content_group"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)


class ContentGroupMembershipRow(Base, TimestampMixin):
    __tablename__ = "content_group_membership"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_group.id"), index=True, nullable=False
    )
    content_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_item.id"), index=True, nullable=False
    )
    added_by: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (UniqueConstraint("group_id", "content_id"),)


class ContentRevisionRow(Base, TimestampMixin):
    __tablename__ = "content_revision"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    content_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_item.id"), nullable=False
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (UniqueConstraint("content_id", "revision_no"),)


class ContentRevisionMediaRow(Base, TimestampMixin):
    __tablename__ = "content_revision_media"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    content_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_revision.id"), index=True, nullable=False
    )
    content_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_item.id"), index=True, nullable=False
    )
    media_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_asset.id"), index=True, nullable=False
    )
    __table_args__ = (UniqueConstraint("content_revision_id", "media_asset_id"),)


class AutomationVersionRow(Base, TimestampMixin):
    __tablename__ = "automation_package_version"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    signature_key_id: Mapped[str] = mapped_column(String(160), nullable=False)
    signature_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    sbom_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    sbom_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    rollout_percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rollout_evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    production_qualified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "name", "version"),)


class RecipeDeploymentRow(Base, TimestampMixin):
    __tablename__ = "recipe_device_deployment"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("automation_package_version.id"), index=True, nullable=False
    )
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("device.id"), index=True, nullable=False
    )
    command_type: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    previous_version_id: Mapped[str | None] = mapped_column(String(36))
    published_by: Mapped[str] = mapped_column(String(36), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "device_id",
            "command_type",
            "idempotency_key",
            name="uq_recipe_deploy_command_key",
        ),
        Index(
            "uq_recipe_deploy_published",
            "tenant_id",
            "device_id",
            "command_type",
            unique=True,
            postgresql_where=text("status = 'PUBLISHED'"),
            sqlite_where=text("status = 'PUBLISHED'"),
        ),
        CheckConstraint("status IN ('PUBLISHED','REVOKED')", name="recipe_deployment_status"),
        Index("ix_recipe_deploy_active", "tenant_id", "device_id", "command_type", "status"),
    )


class RecipeDeploymentActionRow(Base, TimestampMixin):
    __tablename__ = "recipe_deployment_action"
    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("automation_package_version.id"), nullable=False
    )
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ApkArtifactRow(Base, TimestampMixin):
    __tablename__ = "apk_artifact"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    package_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version_name: Mapped[str] = mapped_column(String(120), nullable=False)
    version_code: Mapped[int] = mapped_column(Integer, nullable=False)
    signature_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    min_sdk: Mapped[int] = mapped_column(Integer, nullable=False)
    target_sdk: Mapped[int] = mapped_column(Integer, nullable=False)
    abis: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    sbom_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    sbom_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    analysis_key_id: Mapped[str] = mapped_column(String(160), nullable=False)
    analysis_signature_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_report: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    policy_decision: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "sha256"),)


class PublishPlanRow(Base, TimestampMixin):
    __tablename__ = "publish_plan"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    creator_id: Mapped[str] = mapped_column(String(36), nullable=False)
    content_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_revision.id"), nullable=False
    )
    product_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("product.id"), index=True)
    automation_package_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("automation_package_version.id"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(160), nullable=False)
    schedule: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    execution: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    approval_policy: Mapped[str] = mapped_column(String(64), nullable=False)
    targets: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    workflow_id: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)


class PublishSnapshotRow(Base, TimestampMixin):
    __tablename__ = "publish_snapshot"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("publish_plan.id"), unique=True)
    content_revision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    automation_package_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class PublishTargetRow(Base, TimestampMixin):
    __tablename__ = "publish_target"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("publish_plan.id"), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("publish_snapshot.id"), nullable=False
    )
    account_id: Mapped[str] = mapped_column(String(36), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(36))
    binding_version: Mapped[int | None] = mapped_column(Integer)
    device_id_at_execution: Mapped[str | None] = mapped_column(String(36))
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    result_detail: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ApprovalRow(Base, TimestampMixin):
    __tablename__ = "approval"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("publish_plan.id"), nullable=False)
    creator_id: Mapped[str] = mapped_column(String(36), nullable=False)
    approver_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)


class DeviceLeaseRow(Base, TimestampMixin):
    __tablename__ = "device_lease"
    device_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    lease_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    owner_workflow_id: Mapped[str] = mapped_column(String(255), nullable=False)
    fencing_token: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_type: Mapped[str] = mapped_column(String(16), default="AUTO", nullable=False)


class CommitIntentRow(Base, TimestampMixin):
    __tablename__ = "commit_intent"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    target_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("publish_target.id"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    fencing_token: Mapped[int] = mapped_column(Integer, nullable=False)
    before_commit_evidence_id: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (UniqueConstraint("target_id", "attempt_no"),)


class AuditEventRow(Base):
    __tablename__ = "audit_event"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str] = mapped_column(String(255), nullable=False)
    workflow_id: Mapped[str | None] = mapped_column(String(255))
    device_id: Mapped[str | None] = mapped_column(String(36))
    edge_id: Mapped[str | None] = mapped_column(String(36))
    before_hash: Mapped[str | None] = mapped_column(String(64))
    after_hash: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutboxEventRow(Base):
    __tablename__ = "outbox_event"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_type: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_owner: Mapped[str | None] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)


class OperationTaskRow(Base, TimestampMixin):
    __tablename__ = "operation_task"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    operation_key: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    feature_id: Mapped[str | None] = mapped_column(String(160), index=True)
    module: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    succeeded_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    canceled_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_decision: Mapped[str | None] = mapped_column(String(32))
    approval_reason: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(36))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)


class OperationFeatureConfigDraftRow(Base, TimestampMixin):
    __tablename__ = "operation_feature_config_draft"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    feature_id: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    configuration_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    configuration_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(36), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_operation_feature_config_draft_version"),
        UniqueConstraint(
            "tenant_id",
            "feature_id",
            name="uq_operation_feature_config_draft_tenant_feature",
        ),
    )


class OperationItemRow(Base):
    __tablename__ = "operation_item"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("operation_task.id"), index=True, nullable=False
    )
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    detail: Mapped[str | None] = mapped_column(Text)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("task_id", "resource_id"),)


class DebugSessionRow(Base, TimestampMixin):
    __tablename__ = "debug_session"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    edge_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    lease_id: Mapped[str | None] = mapped_column(String(36), unique=True, index=True)
    fencing_token: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    purpose: Mapped[str] = mapped_column(String(1000), nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    launch_code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    launch_code_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    relay_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    relay_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exchanged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stage: Mapped[str | None] = mapped_column(String(80))
    last_event: Mapped[str | None] = mapped_column(String(160))
    detail: Mapped[str | None] = mapped_column(Text)
    return_url: Mapped[str | None] = mapped_column(String(1024))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(String(36))
    revoke_reason: Mapped[str | None] = mapped_column(Text)


class DebugEvidenceRow(Base, TimestampMixin):
    __tablename__ = "debug_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("debug_session.id"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    object_ref: Mapped[str] = mapped_column(String(1024), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("session_id", "sha256"),)


class MobileEnrollmentRow(Base, TimestampMixin):
    """One-time code used to bind a Companion directly to the control plane."""

    __tablename__ = "mobile_enrollment"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("device.id"), index=True)
    code_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)


class MobileBindingRow(Base, TimestampMixin):
    __tablename__ = "mobile_binding"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("device.id"), index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    app_instance_id: Mapped[str] = mapped_column(String(128), nullable=False)
    companion_version: Mapped[str] = mapped_column(String(128), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("device_id", "app_instance_id"),)


class MobileTaskRow(Base, TimestampMixin):
    __tablename__ = "mobile_task"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("device.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)
    target_package: Mapped[str] = mapped_column(String(255), nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(36), index=True)
    binding_version: Mapped[int | None] = mapped_column(Integer)
    device_id_at_execution: Mapped[str | None] = mapped_column(String(36))
    command_type: Mapped[str | None] = mapped_column(String(80), index=True)
    command_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    recipe_pin: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    business_state: Mapped[str] = mapped_column(String(32), default="QUEUED", index=True, nullable=False)
    control_mode: Mapped[str] = mapped_column(String(16), default="AUTO", nullable=False)
    batch_id: Mapped[str | None] = mapped_column(String(36), index=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stall_reason: Mapped[str | None] = mapped_column(String(160))
    attempt_id: Mapped[str | None] = mapped_column(String(36))
    resume_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pause_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciliation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    lease_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_step: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    detail: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key"),
        Index(
            "uq_mobile_task_device_active",
            "device_id",
            unique=True,
            postgresql_where=text("status IN ('CLAIMED', 'RUNNING')"),
            sqlite_where=text("status IN ('CLAIMED', 'RUNNING')"),
        ),
    )


class MobileTaskEventRow(Base):
    __tablename__ = "mobile_task_event"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mobile_task.id"), index=True, nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    step_index: Mapped[int | None] = mapped_column(Integer)
    step_id: Mapped[str | None] = mapped_column(String(128))
    attempt_id: Mapped[str | None] = mapped_column(String(36))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("task_id", "sequence"),)


class DevicePreviewRow(Base, TimestampMixin):
    """Latest operator-requested Companion screenshot for a mobile-direct device."""

    __tablename__ = "device_preview"
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("device.id"), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(36))
    session_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_by: Mapped[str | None] = mapped_column(String(36))
    capture_interval_ms: Mapped[int] = mapped_column(Integer, default=2_000, nullable=False)
    frame_session_id: Mapped[str | None] = mapped_column(String(36))
    content_type: Mapped[str | None] = mapped_column(String(64))
    sha256: Mapped[str | None] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    image_bytes: Mapped[bytes | None] = mapped_column(LargeBinary)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SourceConnectionRow(Base, TimestampMixin):
    """External data source connection for product/media library."""

    __tablename__ = "source_connection"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    connection_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    secret_ref: Mapped[str | None] = mapped_column(String(512))
    mapping_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_result: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "connection_name"),)


class SyncRunRow(Base, TimestampMixin):
    """Synchronization execution for a source connection."""

    __tablename__ = "sync_run"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_connection.id"), index=True, nullable=False
    )
    run_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cursor_before: Mapped[str | None] = mapped_column(Text)
    cursor_after: Mapped[str | None] = mapped_column(Text)
    records_read: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(36), nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text)


class SourceRecordLinkRow(Base, TimestampMixin):
    """Maps external source records to internal Product/MediaAsset entities."""

    __tablename__ = "source_record_link"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_connection.id"), index=True, nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tombstoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("tenant_id", "connection_id", "external_id"),
        Index("ix_source_record_link_entity", "tenant_id", "entity_kind", "entity_id"),
    )


class SyncErrorRow(Base, TimestampMixin):
    """Row-level synchronization errors with external record context."""

    __tablename__ = "sync_error"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    sync_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sync_run.id"), index=True, nullable=False
    )
    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_connection.id"), index=True, nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    error_code: Mapped[str] = mapped_column(String(80), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(160))
    record_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_sync_error_unresolved", "connection_id", "resolved_at"),)


class Database:
    def __init__(self, settings: Settings) -> None:
        url = settings.resolved_database_url()
        engine_args: dict[str, Any] = {"pool_pre_ping": True}
        if url.endswith(":memory:"):
            engine_args["poolclass"] = StaticPool
        self.engine: AsyncEngine = create_async_engine(url, **engine_args)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def ping(self) -> None:
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    @asynccontextmanager
    async def unit_of_work(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session, session.begin():
            yield session
