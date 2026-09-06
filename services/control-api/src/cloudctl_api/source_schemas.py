"""Source connection schemas and validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceConnectionConfig(BaseModel):
    """Base configuration for a source connection."""

    type: str
    # Additional fields defined by specific source kinds


class CSVFileConfig(BaseModel):
    """Configuration for CSV file source."""

    type: Literal["csv_file"] = "csv_file"
    base_path: str
    file_name: str
    encoding: str = "utf-8"


class SourceConnectionCreate(BaseModel):
    """Request to create a new source connection."""

    connection_name: str = Field(..., min_length=1, max_length=160)
    source_kind: str = Field(..., min_length=1, max_length=80)
    entity_kind: Literal["product", "media"]
    config: dict[str, Any]
    secret_ref: str | None = None
    mapping_version: str = "1.0"


class SourceConnectionResponse(BaseModel):
    """Source connection details."""

    id: str
    tenant_id: str
    connection_name: str
    source_kind: str
    entity_kind: str
    config: dict[str, Any]
    secret_ref: str | None
    mapping_version: str
    status: str
    last_test_at: datetime | None
    last_test_result: str | None
    created_at: datetime
    created_by: str


class SourceRecordPreview(BaseModel):
    """Preview of a single source record before normalization."""

    external_id: str
    raw_data: dict[str, Any]
    normalized_data: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)


class SourcePreviewResponse(BaseModel):
    """Preview result without writing to database."""

    total_read: int
    valid_records: int
    invalid_records: int
    records: list[SourceRecordPreview]
    cursor: str | None = None


class SyncRunRequest(BaseModel):
    """Request to start a synchronization run."""

    connection_id: str
    run_mode: Literal["preview", "full", "incremental"] = "incremental"
    cursor: str | None = None


class SyncRunResponse(BaseModel):
    """Synchronization run status."""

    id: str
    tenant_id: str
    connection_id: str
    run_mode: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    cursor_before: str | None
    cursor_after: str | None
    records_read: int
    records_created: int
    records_updated: int
    records_failed: int
    error_summary: str | None


class SyncErrorResponse(BaseModel):
    """Row-level synchronization error."""

    id: str
    sync_run_id: str
    connection_id: str
    external_id: str
    error_code: str
    error_message: str
    field_name: str | None
    record_snapshot: dict[str, Any] | None
    retry_count: int
    created_at: datetime
    resolved_at: datetime | None
