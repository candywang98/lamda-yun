"""APK release registry and ring rollout policy (U10, apk-release/v1).

Contract: contracts/apk-release/v1/README.md (apk-release/v1@20260917.1,
FROZEN). This module is the *device APK upgrade* track and deliberately
disjoint from the P14 recipe lifecycle: recipes pick the automation logic a
task runs with, releases pick the APK a device installs. Both reuse the same
audit trail, tenant scoping and the Ed25519 admission chain that
``apk_policy`` already applies to ``apk_artifact`` rows upstream.

Invariants implemented here:

- A release is immutable per artifact (``(tenant, artifact)`` unique);
  re-publishing the same artifact id fails with 409 APK_RELEASE_EXISTS.
- Ring rollout: canary/early/all with the device ring derived from
  ``device.labels`` ("ring:<name>"); unlabeled devices only take "all".
- Install candidates (pins) survive release retirement.
- Devices with a RUNNING / PAUSED_WAITING_USER / RECONCILING task (runner
  CLAIMED included — it is the leased preflight of RUNNING) never get an
  install candidate forced onto them: 409 APK_DEVICE_BUSY.
- ``requiresUserConfirmation`` is a requirement statement only; no field in
  this API ever guarantees silent installation (SDK flags cannot override).
- Install receipts (``:report-installed``) are the device's ground truth for
  the install outcome. Only ``outcome=INSTALLED`` with a non-false
  ``signatureMatched`` advances ``apk_release_target`` to ``INSTALLED``;
  FAILED / USER_DECLINED / INTERRUPTED receipts (and a proven signature
  mismatch) are recorded in the audit trail without advancing the rollout
  state, so the candidate stays retryable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, TypeGuard

from cloudctl_domain import (
    Actor,
    ConflictError,
    NotFoundError,
    Permission,
    ValidationError,
    require_permissions,
)
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from .apk_policy import ALLOWED_ABIS
from .auth import current_actor
from .db import (
    ApkArtifactRow,
    ApkReleaseRow,
    ApkReleaseTargetRow,
    Database,
    DeviceRow,
    MobileBindingRow,
    MobileTaskRow,
)
from .mobile_routes import binding as companion_binding
from .repository import ControlRepository

RING_LABEL_PREFIX = "ring"
ALLOWED_RINGS = ("canary", "early", "all")
# Runner states that hold a lease on the device (CLAIMED is the leased
# preflight of RUNNING) plus the blocking business states from
# control-plane/v1 §2.3 — an install must never preempt any of them.
BLOCKING_INSTALL_RUNNER_STATES = ("CLAIMED", "RUNNING")
BLOCKING_INSTALL_BUSINESS_STATES = frozenset({"PAUSED_WAITING_USER", "RECONCILING"})
MIN_CAPABILITY_KEYS = frozenset({"sdkInt", "abis"})


# ---------------------------------------------------------------------------
# Problem codes — subclasses only pin ``code``; app.py's DomainError handler
# renders them as problem+json with the explicit machine-readable code.
# ---------------------------------------------------------------------------


class ApkReleaseExistsError(ConflictError):
    code = "APK_RELEASE_EXISTS"


class ApkReleaseRetiredError(ConflictError):
    code = "APK_RELEASE_RETIRED"


class ApkCandidateExistsError(ConflictError):
    code = "APK_CANDIDATE_EXISTS"


class ApkCandidateStateError(ConflictError):
    code = "APK_CANDIDATE_STATE"


class ApkDeviceBusyError(ConflictError):
    code = "APK_DEVICE_BUSY"


class ApkRingMismatchError(ValidationError):
    code = "APK_RING_MISMATCH"


class ApkCapabilityInsufficientError(ValidationError):
    code = "APK_CAPABILITY_INSUFFICIENT"


class ApkVersionDowngradeError(ValidationError):
    code = "APK_VERSION_DOWNGRADE"


class ApkSchemaIncompatibleError(ValidationError):
    code = "APK_SCHEMA_INCOMPATIBLE"


class ApkDownloadHashMismatchError(ValidationError):
    code = "APK_DOWNLOAD_HASH_MISMATCH"


class ApkArtifactNotAdmittedError(ValidationError):
    code = "APK_ARTIFACT_NOT_ADMITTED"


class ApkReceiptMismatchError(ValidationError):
    code = "APK_RECEIPT_MISMATCH"


# ---------------------------------------------------------------------------
# Request models (strict: unknown fields are rejected, aliases are camelCase)
# ---------------------------------------------------------------------------


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ApkDataSchema(_StrictModel):
    """Data schema compatibility window (contract §1.2)."""

    min_compatible: int = Field(alias="minCompatible", ge=1)
    current: int = Field(ge=1)

    @model_validator(mode="after")
    def _window_ordered(self) -> ApkDataSchema:
        if self.current < self.min_compatible:
            raise ValueError("dataSchema.current must be >= minCompatible")
        return self


class ApkReleaseCreate(_StrictModel):
    artifact_id: str = Field(alias="artifactId", min_length=1, max_length=36)
    ring: str = Field(default="all", max_length=16)
    min_capability: dict[str, Any] = Field(default_factory=dict, alias="minCapability")
    data_schema: ApkDataSchema = Field(alias="dataSchema")
    # Requirement statement only — never a silent-install guarantee (§4).
    requires_user_confirmation: bool = Field(default=True, alias="requiresUserConfirmation")

    @field_validator("ring")
    @classmethod
    def _known_ring(cls, value: str) -> str:
        if value not in ALLOWED_RINGS:
            raise ValueError(f"ring must be one of {list(ALLOWED_RINGS)}")
        return value

    @field_validator("min_capability")
    @classmethod
    def _closed_capability_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(value) - MIN_CAPABILITY_KEYS)
        if unknown:
            raise ValueError(f"minCapability has unknown keys: {unknown}")
        if "sdkInt" in value:
            sdk_int = value["sdkInt"]
            if isinstance(sdk_int, bool) or not isinstance(sdk_int, int) or sdk_int < 21:
                raise ValueError("minCapability.sdkInt must be an integer >= 21")
        if "abis" in value:
            abis = value["abis"]
            if not isinstance(abis, list) or not abis:
                raise ValueError("minCapability.abis must be a non-empty list")
            unsupported = sorted(set(abis) - ALLOWED_ABIS)
            if unsupported:
                raise ValueError(f"minCapability.abis has unsupported entries: {unsupported}")
        return value


class ApkReleaseRetireRequest(_StrictModel):
    reason: str = Field(min_length=1, max_length=500)


class ApkReleaseAssignRequest(_StrictModel):
    target_device_ids: list[str] = Field(alias="targetDeviceIds", min_length=1, max_length=64)


class ApkDownloadedReport(_StrictModel):
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class ApkInstallReceiptReport(_StrictModel):
    """Device-side install receipt (U11 ``ApkInstallReceipt.toWireJson``).

    The device is the only authority on what the installer did; the server
    validates the receipt joins the bound device's own candidate (identity
    fields must match the pinned target + artifact) and never fabricates a
    success the receipt did not claim.
    """

    candidate_id: str = Field(alias="candidateId", min_length=1, max_length=36)
    release_id: str = Field(alias="releaseId", min_length=1, max_length=36)
    package_name: str = Field(alias="packageName", min_length=1, max_length=255)
    attempted_version_code: int = Field(alias="attemptedVersionCode", ge=0)
    outcome: Literal["INSTALLED", "FAILED", "USER_DECLINED", "INTERRUPTED"]
    installed_version_code: int | None = Field(default=None, alias="installedVersionCode", ge=0)
    signature_matched: bool | None = Field(default=None, alias="signatureMatched")
    message: str | None = Field(default=None, max_length=1000)
    completed_at: str = Field(alias="completedAt", min_length=1, max_length=64)

    @field_validator("completed_at")
    @classmethod
    def _iso_instant(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("completedAt must be an ISO-8601 instant") from exc
        if parsed.tzinfo is None:
            raise ValueError("completedAt must carry a timezone offset or Z")
        return value


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _is_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


class ApkReleaseService:
    def __init__(self, database: Database) -> None:
        self.database = database

    # -- operator: release lifecycle -----------------------------------------

    async def create_release(self, actor: Actor, request: ApkReleaseCreate) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.APK_MANAGE)
        try:
            async with self.database.unit_of_work() as session:
                repository = ControlRepository(session, actor)
                artifact = await session.scalar(
                    select(ApkArtifactRow).where(
                        ApkArtifactRow.id == request.artifact_id,
                        ApkArtifactRow.tenant_id == repository.tenant_id,
                    )
                )
                if artifact is None:
                    raise NotFoundError("apk artifact was not found")
                if artifact.scan_status != "CLEAN":
                    raise ApkArtifactNotAdmittedError(
                        "apk artifact has not passed admission policy"
                    )
                existing = await session.scalar(
                    select(ApkReleaseRow).where(
                        ApkReleaseRow.tenant_id == repository.tenant_id,
                        ApkReleaseRow.artifact_id == artifact.id,
                    )
                )
                if existing is not None:
                    raise ApkReleaseExistsError(
                        "this apk artifact was already published and cannot be overwritten"
                    )
                row = ApkReleaseRow(
                    id=repository.new_id(),
                    tenant_id=repository.tenant_id,
                    artifact_id=artifact.id,
                    ring=request.ring,
                    status="ACTIVE",
                    min_capability=dict(request.min_capability),
                    data_schema=request.data_schema.model_dump(mode="json", by_alias=True),
                    requires_user_confirmation=request.requires_user_confirmation,
                    released_by=str(actor.user_id),
                    retired_at=None,
                    retired_by=None,
                    created_at=_now(),
                )
                repository.add(row)
                await repository.flush()
                view = self._release_view(row, artifact)
                repository.audit(
                    action="apk.release.published",
                    resource_type="apk_release",
                    resource_id=row.id,
                    after=view,
                )
                return view
        except IntegrityError as exc:
            raise ApkReleaseExistsError(
                "this apk artifact was already published and cannot be overwritten"
            ) from exc

    async def list_releases(self, actor: Actor) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.APK_MANAGE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            releases = list(
                await session.scalars(
                    select(ApkReleaseRow)
                    .where(ApkReleaseRow.tenant_id == repository.tenant_id)
                    .order_by(ApkReleaseRow.created_at, ApkReleaseRow.id)
                )
            )
            items = []
            for row in releases:
                artifact = await session.get(ApkArtifactRow, row.artifact_id)
                if artifact is None:
                    raise NotFoundError("apk artifact was not found")
                items.append(self._release_view(row, artifact))
            return {"items": items}

    async def get_release(self, actor: Actor, release_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.APK_MANAGE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            row, artifact = await self._release_with_artifact(session, repository, release_id)
            return self._release_view(row, artifact)

    async def retire_release(
        self, actor: Actor, release_id: str, request: ApkReleaseRetireRequest
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.APK_MANAGE)
        async with self.database.unit_of_work() as session:
            repository = ControlRepository(session, actor)
            row, artifact = await self._release_with_artifact(session, repository, release_id)
            if row.status != "ACTIVE":
                raise ApkReleaseRetiredError("apk release is already retired")
            before = self._release_view(row, artifact)
            row.status = "RETIRED"
            row.retired_at = _now()
            row.retired_by = str(actor.user_id)
            view = self._release_view(row, artifact)
            # Deliberately no touching of apk_release_target rows: pins keep
            # resolving for devices that already hold an OFFERED candidate.
            repository.audit(
                action="apk.release.retired",
                resource_type="apk_release",
                resource_id=row.id,
                before=before,
                after=view,
                metadata={"reason": request.reason},
            )
            return view

    async def assign_release(
        self, actor: Actor, release_id: str, request: ApkReleaseAssignRequest
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.APK_MANAGE)
        device_ids = sorted(set(request.target_device_ids))
        try:
            async with self.database.unit_of_work() as session:
                repository = ControlRepository(session, actor)
                release, artifact = await self._release_with_artifact(
                    session, repository, release_id
                )
                if release.status != "ACTIVE":
                    raise ApkReleaseRetiredError(
                        "retired apk releases cannot receive new install candidates"
                    )
                targets: list[ApkReleaseTargetRow] = []
                for device_id in device_ids:
                    # Tenant-scoped with row lock: serializes against claim and
                    # overlapping multi-device assigns (recipe `_change_recipe`
                    # lock-order precedent).
                    device = await repository.device(device_id, for_update=True)
                    self._check_ring(release, device)
                    self._check_capability(release, device)
                    self._check_version(artifact, device)
                    self._check_schema(release, artifact, device)
                    await self._check_device_idle(session, repository.tenant_id, device_id)
                    existing = await session.scalar(
                        select(ApkReleaseTargetRow).where(
                            ApkReleaseTargetRow.tenant_id == repository.tenant_id,
                            ApkReleaseTargetRow.device_id == device_id,
                            ApkReleaseTargetRow.release_id == release.id,
                        )
                    )
                    if existing is not None:
                        targets.append(existing)
                        continue
                    pending_other = await session.scalar(
                        select(ApkReleaseTargetRow).where(
                            ApkReleaseTargetRow.tenant_id == repository.tenant_id,
                            ApkReleaseTargetRow.device_id == device_id,
                            ApkReleaseTargetRow.package_name == artifact.package_name,
                            ApkReleaseTargetRow.status == "OFFERED",
                            ApkReleaseTargetRow.release_id != release.id,
                        )
                    )
                    if pending_other is not None:
                        raise ApkCandidateExistsError(
                            "device already has a pending install candidate for this package"
                        )
                    target = ApkReleaseTargetRow(
                        id=repository.new_id(),
                        tenant_id=repository.tenant_id,
                        release_id=release.id,
                        device_id=device_id,
                        package_name=artifact.package_name,
                        status="OFFERED",
                        requires_user_confirmation=release.requires_user_confirmation,
                        assigned_by=str(actor.user_id),
                        created_at=_now(),
                        updated_at=_now(),
                    )
                    repository.add(target)
                    targets.append(target)
                await repository.flush()
                response = {
                    "release": self._release_view(release, artifact),
                    "targets": [self._target_view(target) for target in targets],
                }
                repository.audit(
                    action="apk.release.assigned",
                    resource_type="apk_release",
                    resource_id=release.id,
                    device_id=device_ids[0] if len(device_ids) == 1 else None,
                    after={"device_ids": device_ids, "targets": response["targets"]},
                    metadata={"device_ids": device_ids},
                )
                return response
        except IntegrityError as exc:
            raise ConflictError(
                "concurrent apk release assignment changed; refresh and retry"
            ) from exc

    # -- companion: device-side candidates ------------------------------------

    async def list_candidates(self, current: MobileBindingRow) -> dict[str, Any]:
        async with self.database.unit_of_work() as session:
            targets = list(
                await session.scalars(
                    select(ApkReleaseTargetRow)
                    .where(
                        ApkReleaseTargetRow.tenant_id == current.tenant_id,
                        ApkReleaseTargetRow.device_id == current.device_id,
                        ApkReleaseTargetRow.status.in_(("OFFERED", "DOWNLOADED")),
                    )
                    .order_by(ApkReleaseTargetRow.created_at, ApkReleaseTargetRow.id)
                )
            )
            items = []
            for target in targets:
                release = await session.get(ApkReleaseRow, target.release_id)
                artifact = (
                    await session.get(ApkArtifactRow, release.artifact_id) if release else None
                )
                if release is None or artifact is None:
                    continue
                items.append(self._candidate_view(target, release, artifact))
            return {"items": items}

    async def report_downloaded(
        self, current: MobileBindingRow, target_id: str, request: ApkDownloadedReport
    ) -> dict[str, Any]:
        async with self.database.unit_of_work() as session:
            target = await session.scalar(
                select(ApkReleaseTargetRow).where(
                    ApkReleaseTargetRow.id == target_id,
                    ApkReleaseTargetRow.tenant_id == current.tenant_id,
                    ApkReleaseTargetRow.device_id == current.device_id,
                )
            )
            if target is None:
                raise NotFoundError("apk install candidate was not found")
            if target.status == "DOWNLOADED":
                release, artifact = await self._release_artifact(session, target.release_id)
                return {
                    "candidateId": target.id,
                    "status": "DOWNLOADED",
                    "sha256": artifact.sha256,
                    "sourceRef": artifact.source_ref,
                }
            if target.status != "OFFERED":
                raise ApkCandidateStateError(
                    "only an OFFERED install candidate can report a download"
                )
            # A RETIRED release still serves its pinned candidates (§1.3).
            release, artifact = await self._release_artifact(session, target.release_id)
            observed = request.sha256.lower()
            if observed != artifact.sha256:
                raise ApkDownloadHashMismatchError(
                    "downloaded apk hash does not match the release; candidate stays OFFERED"
                )
            target.status = "DOWNLOADED"
            target.updated_at = _now()
            device_actor = Actor(
                tenant_id=uuid.UUID(current.tenant_id),
                user_id=uuid.UUID(current.device_id),
                roles=frozenset(),
                mfa=False,
                request_id=f"companion:{current.id}",
            )
            repository = ControlRepository(session, device_actor)
            repository.audit(
                action="apk.release.downloaded",
                resource_type="apk_release_target",
                resource_id=target.id,
                device_id=current.device_id,
                after={"releaseId": release.id, "sha256": artifact.sha256},
            )
            return {
                "candidateId": target.id,
                "status": "DOWNLOADED",
                "sha256": artifact.sha256,
                "sourceRef": artifact.source_ref,
            }

    async def report_installed(
        self, current: MobileBindingRow, target_id: str, request: ApkInstallReceiptReport
    ) -> dict[str, Any]:
        """Terminal install receipt (U11 seam, WIRE2 wiring).

        Semantics:

        - tenant/device scoped exactly like ``report_downloaded``: a candidate
          of another device (or tenant, or a nonexistent id) is a plain 404;
        - the receipt's identity fields must join the pinned target and its
          artifact, otherwise 422 ``APK_RECEIPT_MISMATCH`` (never a silent
          re-attribution to a different release/package);
        - only ``outcome=INSTALLED`` with ``signatureMatched`` not false
          advances the target to ``INSTALLED`` (the rollout's only terminal
          state — the status CHECK constraint has no FAILED value; failures
          keep the candidate retryable at DOWNLOADED/OFFERED);
        - a replayed success receipt against an already-INSTALLED target is an
          idempotent no-op 200 (the ``report_downloaded`` precedent: no second
          audit event);
        - non-advancing receipts are recorded as ``apk.release.install_receipt``
          audit events carrying the full receipt payload.
        """
        async with self.database.unit_of_work() as session:
            target = await session.scalar(
                select(ApkReleaseTargetRow).where(
                    ApkReleaseTargetRow.id == target_id,
                    ApkReleaseTargetRow.tenant_id == current.tenant_id,
                    ApkReleaseTargetRow.device_id == current.device_id,
                )
            )
            if target is None:
                raise NotFoundError("apk install candidate was not found")
            release, artifact = await self._release_artifact(session, target.release_id)
            mismatched = [
                label
                for label, claimed, pinned in (
                    ("candidateId", request.candidate_id, target.id),
                    ("releaseId", request.release_id, target.release_id),
                    ("packageName", request.package_name, target.package_name),
                    ("attemptedVersionCode", request.attempted_version_code, artifact.version_code),
                )
                if claimed != pinned
            ]
            if mismatched:
                raise ApkReceiptMismatchError(
                    f"install receipt does not match the pinned candidate: {mismatched}"
                )
            received = _now()
            receipt = request.model_dump(mode="json", by_alias=True)
            counts_as_installed = (
                request.outcome == "INSTALLED" and request.signature_matched is not False
            )
            already_installed = target.status == "INSTALLED"
            if not already_installed:
                device_actor = Actor(
                    tenant_id=uuid.UUID(current.tenant_id),
                    user_id=uuid.UUID(current.device_id),
                    roles=frozenset(),
                    mfa=False,
                    request_id=f"companion:{current.id}",
                )
                repository = ControlRepository(session, device_actor)
                if counts_as_installed:
                    target.status = "INSTALLED"
                    target.updated_at = received
                    repository.audit(
                        action="apk.release.installed",
                        resource_type="apk_release_target",
                        resource_id=target.id,
                        device_id=current.device_id,
                        after={
                            "releaseId": release.id,
                            "status": "INSTALLED",
                            "installedVersionCode": request.installed_version_code,
                            "signatureMatched": request.signature_matched,
                        },
                        metadata={"receipt": receipt},
                    )
                else:
                    # FAILED / USER_DECLINED / INTERRUPTED (or a proven signature
                    # mismatch): evidence only — the candidate stays retryable.
                    repository.audit(
                        action="apk.release.install_receipt",
                        resource_type="apk_release_target",
                        resource_id=target.id,
                        device_id=current.device_id,
                        after={"releaseId": release.id, "status": target.status},
                        metadata={"receipt": receipt},
                    )
            return {
                "candidateId": target.id,
                "status": target.status,
                "outcome": request.outcome,
                "receivedAt": received.isoformat(),
            }

    # -- shared helpers --------------------------------------------------------

    async def _release_artifact(
        self, session: Any, release_id: str
    ) -> tuple[ApkReleaseRow, ApkArtifactRow]:
        release = await session.get(ApkReleaseRow, release_id)
        if release is None:
            raise NotFoundError("apk release was not found")
        artifact = await session.get(ApkArtifactRow, release.artifact_id)
        if artifact is None:
            raise NotFoundError("apk artifact was not found")
        return release, artifact

    async def _release_with_artifact(
        self, session: Any, repository: ControlRepository, release_id: str
    ) -> tuple[ApkReleaseRow, ApkArtifactRow]:
        row = await session.scalar(
            select(ApkReleaseRow).where(
                ApkReleaseRow.id == release_id,
                ApkReleaseRow.tenant_id == repository.tenant_id,
            )
        )
        if row is None:
            raise NotFoundError("apk release was not found")
        artifact = await session.get(ApkArtifactRow, row.artifact_id)
        if artifact is None:
            raise NotFoundError("apk artifact was not found")
        return row, artifact

    @staticmethod
    def _device_ring(device: DeviceRow) -> str | None:
        for label in device.labels or []:
            if isinstance(label, str) and label.startswith(f"{RING_LABEL_PREFIX}:"):
                return label[len(RING_LABEL_PREFIX) + 1 :]
        return None

    @classmethod
    def _check_ring(cls, release: ApkReleaseRow, device: DeviceRow) -> None:
        if release.ring == "all":
            return
        device_ring = cls._device_ring(device)
        if device_ring != release.ring:
            raise ApkRingMismatchError(
                f"release ring '{release.ring}' does not match device ring "
                f"'{device_ring or 'unlabeled'}'"
            )

    @staticmethod
    def _check_capability(release: ApkReleaseRow, device: DeviceRow) -> None:
        requirements = release.min_capability or {}
        capabilities = device.capabilities or {}
        required_sdk = requirements.get("sdkInt")
        if _is_int(required_sdk):
            device_sdk = capabilities.get("sdkInt")
            if not _is_int(device_sdk) or device_sdk < required_sdk:
                raise ApkCapabilityInsufficientError(
                    f"device sdkInt {device_sdk} does not meet the required {required_sdk}"
                )
        required_abis = requirements.get("abis")
        if required_abis:
            device_abis = capabilities.get("abis")
            if not isinstance(device_abis, list) or not set(required_abis) <= set(device_abis):
                raise ApkCapabilityInsufficientError(
                    f"device ABIs do not cover the required set {sorted(set(required_abis))}"
                )

    @staticmethod
    def _check_version(artifact: ApkArtifactRow, device: DeviceRow) -> None:
        installed = (device.target_app_versions or {}).get(artifact.package_name)
        if installed is None:
            return
        try:
            installed_code = int(str(installed))
        except (TypeError, ValueError):
            return
        if installed_code >= artifact.version_code:
            raise ApkVersionDowngradeError(
                f"device already runs versionCode {installed_code}; installing "
                f"{artifact.version_code} would be a downgrade"
            )

    @staticmethod
    def _check_schema(release: ApkReleaseRow, artifact: ApkArtifactRow, device: DeviceRow) -> None:
        try:
            min_compatible = int((release.data_schema or {})["minCompatible"])
        except (KeyError, TypeError, ValueError):
            return
        reported = (device.capabilities or {}).get("dataSchemaVersions", {})
        version = reported.get(artifact.package_name) if isinstance(reported, dict) else None
        # Only a provably older data schema blocks the upgrade; devices that
        # do not report the key stay eligible (contract §3.5).
        if _is_int(version) and version < min_compatible:
            raise ApkSchemaIncompatibleError(
                f"device data schema {version} is older than the release's "
                f"minimum compatible {min_compatible}"
            )

    @staticmethod
    async def _check_device_idle(session: Any, tenant_id: str, device_id: str) -> None:
        busy = await session.scalar(
            select(MobileTaskRow.id).where(
                MobileTaskRow.tenant_id == tenant_id,
                MobileTaskRow.device_id == device_id,
                or_(
                    MobileTaskRow.status.in_(BLOCKING_INSTALL_RUNNER_STATES),
                    MobileTaskRow.business_state.in_(BLOCKING_INSTALL_BUSINESS_STATES),
                ),
            )
        )
        if busy is not None:
            raise ApkDeviceBusyError(
                "device has a RUNNING / PAUSED_WAITING_USER / RECONCILING task; "
                "install preemption is forbidden"
            )

    @staticmethod
    def _release_view(row: ApkReleaseRow, artifact: ApkArtifactRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "artifactId": row.artifact_id,
            "packageName": artifact.package_name,
            "versionCode": artifact.version_code,
            "versionName": artifact.version_name,
            "sha256": artifact.sha256,
            "signatureDigest": artifact.signature_digest,
            "ring": row.ring,
            "status": row.status,
            "minCapability": row.min_capability,
            "dataSchema": row.data_schema,
            "requiresUserConfirmation": row.requires_user_confirmation,
            "releasedBy": row.released_by,
            "releasedAt": _aware(row.created_at).isoformat(),
            "retiredAt": _aware(row.retired_at).isoformat() if row.retired_at else None,
            "retiredBy": row.retired_by,
        }

    @staticmethod
    def _target_view(row: ApkReleaseTargetRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "releaseId": row.release_id,
            "deviceId": row.device_id,
            "packageName": row.package_name,
            "status": row.status,
            "requiresUserConfirmation": row.requires_user_confirmation,
            "assignedBy": row.assigned_by,
            "assignedAt": _aware(row.created_at).isoformat(),
            "updatedAt": _aware(row.updated_at).isoformat(),
        }

    @staticmethod
    def _candidate_view(
        target: ApkReleaseTargetRow, release: ApkReleaseRow, artifact: ApkArtifactRow
    ) -> dict[str, Any]:
        return {
            "candidateId": target.id,
            "releaseId": release.id,
            "releaseStatus": release.status,
            "status": target.status,
            "packageName": artifact.package_name,
            "versionCode": artifact.version_code,
            "versionName": artifact.version_name,
            "sha256": artifact.sha256,
            "signatureDigest": artifact.signature_digest,
            "sourceRef": artifact.source_ref,
            "ring": release.ring,
            "dataSchema": release.data_schema,
            "requiresUserConfirmation": target.requires_user_confirmation,
            "assignedAt": _aware(target.created_at).isoformat(),
        }


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------

operator_router = APIRouter(prefix="/api/v1/apk-releases", tags=["apk-releases"])
companion_router = APIRouter(prefix="/companion/v2/apk", tags=["apk-releases-companion"])


def service(request: Request) -> ApkReleaseService:
    return ApkReleaseService(request.app.state.database)


Service = Annotated[ApkReleaseService, Depends(service)]
ActorDep = Annotated[Actor, Depends(current_actor)]
Binding = Annotated[MobileBindingRow, Depends(companion_binding)]


@operator_router.post("", status_code=status.HTTP_201_CREATED)
async def create_apk_release(
    body: ApkReleaseCreate, actor: ActorDep, releases: Service
) -> dict[str, Any]:
    return await releases.create_release(actor, body)


@operator_router.get("")
async def list_apk_releases(actor: ActorDep, releases: Service) -> dict[str, Any]:
    return await releases.list_releases(actor)


@operator_router.get("/{release_id}")
async def get_apk_release(release_id: str, actor: ActorDep, releases: Service) -> dict[str, Any]:
    return await releases.get_release(actor, release_id)


@operator_router.post("/{release_id}:retire")
async def retire_apk_release(
    release_id: str, body: ApkReleaseRetireRequest, actor: ActorDep, releases: Service
) -> dict[str, Any]:
    return await releases.retire_release(actor, release_id, body)


@operator_router.post("/{release_id}:assign")
async def assign_apk_release(
    release_id: str, body: ApkReleaseAssignRequest, actor: ActorDep, releases: Service
) -> dict[str, Any]:
    return await releases.assign_release(actor, release_id, body)


@companion_router.get("/candidates")
async def list_install_candidates(current: Binding, releases: Service) -> dict[str, Any]:
    return await releases.list_candidates(current)


@companion_router.post("/candidates/{target_id}:report-downloaded")
async def report_candidate_downloaded(
    target_id: str, body: ApkDownloadedReport, current: Binding, releases: Service
) -> dict[str, Any]:
    return await releases.report_downloaded(current, target_id, body)


@companion_router.post("/candidates/{target_id}:report-installed")
async def report_candidate_installed(
    target_id: str, body: ApkInstallReceiptReport, current: Binding, releases: Service
) -> dict[str, Any]:
    return await releases.report_installed(current, target_id, body)
