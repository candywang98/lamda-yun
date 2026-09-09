"""HTTP request and response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class TenantCreate(ApiModel):
    name: str = Field(min_length=1, max_length=160)


class UserCreate(ApiModel):
    oidc_subject: str = Field(alias="oidcSubject", min_length=1, max_length=255)
    roles: list[str]


class RoleUpdate(ApiModel):
    roles: list[str] = Field(min_length=1)


class EdgeCreate(ApiModel):
    logical_name: str = Field(alias="logicalName", min_length=1, max_length=160)
    certificate_fingerprint: str = Field(alias="certificateFingerprint", min_length=16)


class DeviceCreate(ApiModel):
    edge_id: str = Field(alias="edgeId")
    logical_name: str = Field(alias="logicalName", min_length=1, max_length=160)
    android_version: str | None = Field(default=None, alias="androidVersion")
    lamda_version: str | None = Field(default=None, alias="lamdaVersion")
    target_app_versions: dict[str, str] = Field(default_factory=dict, alias="targetAppVersions")
    capabilities: dict[str, Any] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)


class MaintenanceRequest(ApiModel):
    enabled: bool
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int | None = Field(default=None, alias="expectedVersion")


class PlatformAccountCreate(ApiModel):
    platform: str = Field(min_length=1, max_length=160)
    external_subject_ref: str = Field(alias="externalSubjectRef", min_length=1, max_length=255)
    display_label: str = Field(alias="displayLabel", min_length=1, max_length=160)
    secret_ref: str = Field(alias="secretRef", min_length=8, max_length=512)
    authorization_basis: str = Field(alias="authorizationBasis", min_length=3, max_length=1000)
    expires_at: datetime | None = Field(default=None, alias="expiresAt")

    @field_validator("secret_ref")
    @classmethod
    def safe_secret_reference(cls, value: str) -> str:
        if not value.startswith(("vault://", "secret://", "aws-secretsmanager://")):
            raise ValueError("secretRef must use an approved secret-store URI")
        if any(character.isspace() for character in value):
            raise ValueError("secretRef cannot contain whitespace")
        return value


class AccountDeviceBind(ApiModel):
    device_id: str = Field(alias="deviceId", min_length=1, max_length=36)
    confirmation_note: str = Field(alias="confirmationNote", min_length=3, max_length=1000)


class AccountStatusUpdate(ApiModel):
    status: Literal["AUTHORIZED", "SUSPENDED", "REVOKED"]
    reason: str = Field(min_length=3, max_length=1000)
    expected_version: int | None = Field(default=None, alias="expectedVersion")


class MediaCreate(ApiModel):
    sha256: str
    object_key: str = Field(alias="objectKey", min_length=1)
    content_type: str = Field(alias="contentType", min_length=1)
    size_bytes: int = Field(alias="sizeBytes", ge=0)
    source_asset_id: str | None = Field(default=None, alias="sourceAssetId")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sha256")
    @classmethod
    def valid_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(
            character not in "0123456789abcdefABCDEF" for character in value
        ):
            raise ValueError("sha256 must be 64 hexadecimal characters")
        return value.lower()


class MediaTaxonomyUpdate(ApiModel):
    tags: list[str] = Field(default_factory=list, max_length=30)
    group_ids: list[str] = Field(default_factory=list, alias="groupIds", max_length=30)


class ProductCreate(ApiModel):
    spu_code: str = Field(alias="spuCode", min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)
    category: str = Field(min_length=1, max_length=160)
    price: str = Field(pattern=r"^[0-9]+(\.[0-9]{1,2})?$")
    stock: int = Field(ge=0)
    media_asset_ids: list[str] = Field(default_factory=list, alias="mediaAssetIds", max_length=50)
    attributes: dict[str, Any] = Field(default_factory=dict)


class ProductUpdate(ProductCreate):
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class ProductArchiveRequest(ApiModel):
    reason: str = Field(min_length=3, max_length=1000)


class ProductMediaUpdateItem(ApiModel):
    media_asset_id: str = Field(alias="mediaAssetId", min_length=1, max_length=36)
    sort_order: int = Field(alias="sortOrder", ge=0)
    role: Literal["cover", "detail", "video"]


class ProductMediaUpdate(ApiModel):
    expected_revision: int = Field(alias="expectedRevision", ge=1)
    items: list[ProductMediaUpdateItem] = Field(max_length=50)


class ProductBatchUpdatePrice(ApiModel):
    product_ids: list[str] = Field(alias="productIds", min_length=1, max_length=100)
    price: str = Field(pattern=r"^[0-9]+(\.[0-9]{1,2})?$")


class ProductBatchUpdateGroup(ApiModel):
    product_ids: list[str] = Field(alias="productIds", min_length=1, max_length=100)
    group_id: str = Field(alias="groupId", min_length=1, max_length=36)


class ProductBatchDelete(ApiModel):
    product_ids: list[str] = Field(alias="productIds", min_length=1, max_length=100)
    reason: str = Field(min_length=3, max_length=1000)


class ProductImportItem(ApiModel):
    spu_code: str = Field(alias="spuCode", min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)
    category: str = Field(min_length=1, max_length=160)
    price: str = Field(pattern=r"^[0-9]+(\.[0-9]{1,2})?$")
    stock: int = Field(ge=0)
    image_urls: list[str] = Field(default_factory=list, alias="imageUrls", max_length=50)
    group_id: str | None = Field(default=None, alias="groupId")


class ProductImportRequest(ApiModel):
    items: list[ProductImportItem] = Field(min_length=1, max_length=100)
    group_id: str | None = Field(default=None, alias="groupId")


class ProductFilterRequest(ApiModel):
    search: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=160)
    group_id: str | None = Field(default=None, alias="groupId")
    min_price: str | None = Field(default=None, alias="minPrice", pattern=r"^[0-9]+(\.[0-9]{1,2})?$")
    max_price: str | None = Field(default=None, alias="maxPrice", pattern=r"^[0-9]+(\.[0-9]{1,2})?$")
    status: Literal["ACTIVE", "ARCHIVED", "ALL"] | None = Field(default="ACTIVE")


class MediaUploadCreate(ApiModel):
    file_name: str = Field(alias="fileName", min_length=1, max_length=255)
    sha256: str
    content_type: str = Field(alias="contentType", min_length=1, max_length=160)
    size_bytes: int = Field(alias="sizeBytes", ge=1, le=5 * 1024 * 1024 * 1024)
    source_asset_id: str | None = Field(default=None, alias="sourceAssetId")
    derivative_profile_id: str | None = Field(
        default=None, alias="derivativeProfileId", min_length=1, max_length=160
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sha256")
    @classmethod
    def valid_sha256(cls, value: str) -> str:
        return MediaCreate.valid_sha256(value)

    @field_validator("file_name")
    @classmethod
    def safe_file_name(cls, value: str) -> str:
        if value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("fileName must not contain a path")
        return value


class MediaUploadComplete(ApiModel):
    pass


class MediaDerivativeCreate(ApiModel):
    profile_id: str = Field(alias="profileId", min_length=1, max_length=160)


class MediaDerivativeResult(ApiModel):
    status: Literal["SUCCEEDED", "FAILED"]
    output_asset_id: str | None = Field(default=None, alias="outputAssetId")
    error_code: str | None = Field(default=None, alias="errorCode", max_length=80)
    detail: str | None = Field(default=None, max_length=2000)


class ContentCreate(ApiModel):
    title: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any]
    group_id: str | None = Field(default=None, alias="groupId", min_length=1, max_length=36)

    @field_validator("payload")
    @classmethod
    def valid_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        from .content_payload import validate_content_payload

        return validate_content_payload(value)


class RevisionCreate(ApiModel):
    payload: dict[str, Any]
    group_id: str | None = Field(default=None, alias="groupId", min_length=1, max_length=36)

    @field_validator("payload")
    @classmethod
    def valid_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        from .content_payload import validate_content_payload

        return validate_content_payload(value)


class ContentGroupCreate(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)


class MediaGroupUpdate(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)


class ContentGroupMembershipCreate(ApiModel):
    content_id: str = Field(alias="contentId", min_length=1, max_length=36)


class ContentArchiveRequest(ApiModel):
    reason: str = Field(min_length=3, max_length=1000)


class ContentXianyuDispatchRequest(ApiModel):
    device_id: str = Field(alias="deviceId", min_length=1, max_length=36)
    listing_price: str | None = Field(
        default=None,
        alias="listingPrice",
        min_length=1,
        max_length=32,
        pattern=r"^[0-9]+(\.[0-9]{1,2})?$",
    )


class AutomationPackageCreate(ApiModel):
    artifact_sha256: str = Field(alias="artifactSha256")
    manifest: dict[str, Any]
    sbom_ref: str = Field(alias="sbomRef", min_length=1)
    sbom_sha256: str = Field(alias="sbomSha256")
    signature: str = Field(min_length=1)

    @field_validator("artifact_sha256", "sbom_sha256")
    @classmethod
    def valid_digest(cls, value: str) -> str:
        if len(value) != 64 or any(
            character not in "0123456789abcdefABCDEF" for character in value
        ):
            raise ValueError("digest must be 64 hexadecimal characters")
        return value.lower()


class RolloutEvidenceCreate(ApiModel):
    sample_size: int = Field(alias="sampleSize", ge=0)
    success_count: int = Field(alias="successCount", ge=0)
    failure_count: int = Field(alias="failureCount", ge=0)
    safety_violations: int = Field(alias="safetyViolations", ge=0)
    p95_duration_ms: int = Field(alias="p95DurationMs", ge=0)


class AutomationPromotionRequest(ApiModel):
    target_percentage: Literal[5, 25, 100] = Field(alias="targetPercentage")
    evidence: RolloutEvidenceCreate


class RecipePublishRequest(ApiModel):
    target_device_ids: list[str] = Field(alias="targetDeviceIds", min_length=1, max_length=32)
    idempotency_key: str = Field(alias="idempotencyKey", min_length=8, max_length=128)


class ApkFinding(ApiModel):
    rule_id: str = Field(alias="ruleId", min_length=1, max_length=160)
    severity: Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    title: str = Field(min_length=1, max_length=500)


class ApkAnalysisReport(ApiModel):
    key_id: str = Field(alias="keyId", min_length=1, max_length=160)
    analyzer: str = Field(min_length=1, max_length=160)
    analyzer_version: str = Field(alias="analyzerVersion", min_length=1, max_length=80)
    analyzed_at: datetime = Field(alias="analyzedAt")
    artifact_sha256: str = Field(alias="artifactSha256")
    package_name: str = Field(alias="packageName", min_length=1, max_length=255)
    version_name: str = Field(alias="versionName", min_length=1, max_length=120)
    version_code: int = Field(alias="versionCode", ge=0)
    signature_digest: str = Field(alias="signatureDigest")
    min_sdk: int = Field(alias="minSdk", ge=21)
    target_sdk: int = Field(alias="targetSdk", ge=21)
    abis: list[str] = Field(min_length=1)
    permissions: list[str]
    sbom_sha256: str = Field(alias="sbomSha256")
    debuggable: bool
    uses_cleartext_traffic: bool = Field(alias="usesCleartextTraffic")
    verdict: Literal["CLEAN", "REJECTED", "PENDING"]
    findings: list[ApkFinding] = Field(default_factory=list)

    @field_validator("artifact_sha256", "signature_digest", "sbom_sha256")
    @classmethod
    def valid_digest(cls, value: str) -> str:
        if len(value) != 64 or any(
            character not in "0123456789abcdefABCDEF" for character in value
        ):
            raise ValueError("digest must be 64 hexadecimal characters")
        return value.lower()


class ApkArtifactCreate(ApiModel):
    sha256: str
    package_name: str = Field(alias="packageName")
    version_name: str = Field(alias="versionName")
    version_code: int = Field(alias="versionCode", ge=0)
    signature_digest: str = Field(alias="signatureDigest")
    min_sdk: int = Field(alias="minSdk", ge=21)
    target_sdk: int = Field(alias="targetSdk", ge=21)
    abis: list[str]
    permissions: list[str]
    sbom_ref: str = Field(alias="sbomRef")
    sbom_sha256: str = Field(alias="sbomSha256")
    source_ref: str = Field(alias="sourceRef")
    analysis_report: ApkAnalysisReport = Field(alias="analysisReport")
    analysis_signature: str = Field(alias="analysisSignature", min_length=1)

    @field_validator("sha256", "signature_digest", "sbom_sha256")
    @classmethod
    def valid_digest(cls, value: str) -> str:
        if len(value) != 64 or any(
            character not in "0123456789abcdefABCDEF" for character in value
        ):
            raise ValueError("digest must be 64 hexadecimal characters")
        return value.lower()


class PublishPlanCreate(ApiModel):
    content_revision_id: str = Field(alias="contentRevisionId")
    product_id: str | None = Field(default=None, alias="productId", max_length=36)
    platform: str
    targets: list[dict[str, Any]] = Field(min_length=1)
    schedule: dict[str, Any]
    execution: dict[str, Any]
    approval_policy: Literal["NONE", "BEFORE_START", "BEFORE_COMMIT"] = Field(
        alias="approvalPolicy"
    )
    automation_package_version_id: str = Field(alias="automationPackageVersionId")


class ApprovalRequest(ApiModel):
    decision: Literal["APPROVED", "REJECTED"]
    reason: str | None = Field(default=None, max_length=1000)


class CommitIntentCreate(ApiModel):
    fencing_token: int = Field(alias="fencingToken", ge=1)
    before_commit_evidence_id: str = Field(alias="beforeCommitEvidenceId")


class LeaseRequest(ApiModel):
    owner_workflow_id: str = Field(alias="ownerWorkflowId", min_length=1, max_length=255)
    ttl_seconds: int = Field(default=60, alias="ttlSeconds", ge=10, le=300)


class TargetStateUpdate(ApiModel):
    state: str
    detail: str | None = Field(default=None, max_length=2000)


class ProblemDetails(ApiModel):
    type: str
    title: str
    status: int
    code: str
    detail: str
    correlation_id: str
    retryable: bool
    fields: dict[str, str] = Field(default_factory=dict)


class EventView(ApiModel):
    id: str
    tenant_id: str = Field(alias="tenantId")
    type: str
    aggregate_type: str = Field(alias="aggregateType")
    aggregate_id: str = Field(alias="aggregateId")
    payload: dict[str, Any]
    occurred_at: datetime = Field(alias="occurredAt")


class RecipeRollbackRequest(RecipePublishRequest):
    expected_current_version_id: str = Field(
        alias="expectedCurrentVersionId", min_length=1, max_length=128
    )
