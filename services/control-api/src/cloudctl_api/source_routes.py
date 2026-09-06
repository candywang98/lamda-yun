"""API routes for source connections and synchronization."""

from __future__ import annotations

from typing import Annotated, Any, cast

from cloudctl_domain import Actor
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from .auth import current_actor
from .db import Database, SourceConnectionRow, SyncErrorRow, SyncRunRow
from .media_store import ObjectStore
from .source_schemas import (
    SourceConnectionCreate,
    SourceConnectionResponse,
    SourcePreviewResponse,
    SyncErrorResponse,
    SyncRunRequest,
    SyncRunResponse,
)
from .source_service import create_connector, execute_sync_run, preview_source

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])

ActorDependency = Annotated[Actor, Depends(current_actor)]


def get_database(request: Request) -> Database:
    """Get database from app state."""
    return cast(Database, request.app.state.database)


def get_object_store(request: Request) -> ObjectStore:
    """Get object store from app state."""
    return cast(ObjectStore, request.app.state.object_store)


DatabaseDependency = Annotated[Database, Depends(get_database)]
ObjectStoreDependency = Annotated[ObjectStore, Depends(get_object_store)]


@router.post("/connections", response_model=SourceConnectionResponse, status_code=201)
async def create_source_connection(
    body: SourceConnectionCreate,
    actor: ActorDependency,
    database: DatabaseDependency,
) -> Any:
    """Create a new source connection."""
    from datetime import UTC, datetime
    from uuid import uuid4
    
    async with database.session_factory() as session:
        # Check for duplicate name
        stmt = select(SourceConnectionRow).where(
            SourceConnectionRow.tenant_id == str(actor.tenant_id),
            SourceConnectionRow.connection_name == body.connection_name,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(status_code=409, detail="Connection name already exists")
        
        # Create connection
        connection = SourceConnectionRow(
            id=str(uuid4()),
            tenant_id=str(actor.tenant_id),
            connection_name=body.connection_name,
            source_kind=body.source_kind,
            entity_kind=body.entity_kind,
            config=body.config,
            secret_ref=body.secret_ref,
            mapping_version=body.mapping_version,
            status="active",
            created_by=str(actor.user_id),
            created_at=datetime.now(UTC),
        )
        session.add(connection)
        await session.commit()
        
        return SourceConnectionResponse(
            id=connection.id,
            tenant_id=connection.tenant_id,
            connection_name=connection.connection_name,
            source_kind=connection.source_kind,
            entity_kind=connection.entity_kind,
            config=connection.config,
            secret_ref=connection.secret_ref,
            mapping_version=connection.mapping_version,
            status=connection.status,
            last_test_at=connection.last_test_at,
            last_test_result=connection.last_test_result,
            created_at=connection.created_at,
            created_by=connection.created_by,
        )


@router.get("/connections", response_model=list[SourceConnectionResponse])
async def list_source_connections(
    actor: ActorDependency,
    database: DatabaseDependency,
) -> Any:
    """List all source connections for the tenant."""
    async with database.session_factory() as session:
        stmt = select(SourceConnectionRow).where(
            SourceConnectionRow.tenant_id == str(actor.tenant_id)
        ).order_by(SourceConnectionRow.created_at.desc())
        
        result = await session.execute(stmt)
        connections = result.scalars().all()
        
        return [
            SourceConnectionResponse(
                id=conn.id,
                tenant_id=conn.tenant_id,
                connection_name=conn.connection_name,
                source_kind=conn.source_kind,
                entity_kind=conn.entity_kind,
                config=conn.config,
                secret_ref=conn.secret_ref,
                mapping_version=conn.mapping_version,
                status=conn.status,
                last_test_at=conn.last_test_at,
                last_test_result=conn.last_test_result,
                created_at=conn.created_at,
                created_by=conn.created_by,
            )
            for conn in connections
        ]


@router.post("/connections/{connection_id}/preview", response_model=SourcePreviewResponse)
async def preview_source_connection(
    connection_id: str,
    actor: ActorDependency,
    database: DatabaseDependency,
) -> Any:
    """Preview records from a source connection without writing to database."""
    from datetime import UTC, datetime
    
    async with database.session_factory() as session:
        # Get connection
        stmt = select(SourceConnectionRow).where(
            SourceConnectionRow.id == connection_id,
            SourceConnectionRow.tenant_id == str(actor.tenant_id),
        )
        result = await session.execute(stmt)
        connection = result.scalar_one_or_none()
        
        if not connection:
            raise HTTPException(status_code=404, detail="Connection not found")
        
        # Preview
        preview = await preview_source(
            source_kind=connection.source_kind,
            config=connection.config,
            secret=None,  # TODO: resolve secret_ref
            page_size=10,
        )
        
        # Update test result
        connection.last_test_at = datetime.now(UTC)
        if preview.invalid_records == 0 and preview.total_read > 0:
            connection.last_test_result = f"Success: {preview.total_read} records read"
        elif preview.total_read == 0:
            connection.last_test_result = "No records found"
        else:
            valid = preview.valid_records
            total = preview.total_read
            connection.last_test_result = f"Partial: {valid}/{total} valid"
        
        await session.commit()
        
        return preview


@router.post("/connections/{connection_id}/sync", response_model=SyncRunResponse, status_code=202)
async def start_sync_run(
    connection_id: str,
    body: SyncRunRequest,
    actor: ActorDependency,
    database: DatabaseDependency,
    object_store: ObjectStoreDependency,
) -> Any:
    """Start a synchronization run for a connection."""
    async with database.session_factory() as session:
        # Get connection
        stmt = select(SourceConnectionRow).where(
            SourceConnectionRow.id == connection_id,
            SourceConnectionRow.tenant_id == str(actor.tenant_id),
        )
        result = await session.execute(stmt)
        connection = result.scalar_one_or_none()
        
        if not connection:
            raise HTTPException(status_code=404, detail="Connection not found")
        
        # Create connector
        connector = create_connector(
            source_kind=connection.source_kind,
            config=connection.config,
            secret=None,  # TODO: resolve secret_ref
        )
        
        # Execute sync
        sync_result = await execute_sync_run(
            session=session,
            connection_id=connection.id,
            tenant_id=str(actor.tenant_id),
            triggered_by=str(actor.user_id),
            connector=connector,
            object_store=object_store,
            run_mode=body.run_mode,
            page_size=100,
        )
        
        await session.commit()
        
        # Get the created sync run
        stmt = select(SyncRunRow).where(SyncRunRow.id == sync_result["sync_run_id"])
        result = await session.execute(stmt)
        sync_run = result.scalar_one()
        
        return SyncRunResponse(
            id=sync_run.id,
            tenant_id=sync_run.tenant_id,
            connection_id=sync_run.connection_id,
            run_mode=sync_run.run_mode,
            status=sync_run.status,
            started_at=sync_run.started_at,
            completed_at=sync_run.completed_at,
            cursor_before=sync_run.cursor_before,
            cursor_after=sync_run.cursor_after,
            records_read=sync_run.records_read,
            records_created=sync_run.records_created,
            records_updated=sync_run.records_updated,
            records_failed=sync_run.records_failed,
            error_summary=sync_run.error_summary,
        )


@router.get("/connections/{connection_id}/runs", response_model=list[SyncRunResponse])
async def list_sync_runs(
    connection_id: str,
    actor: ActorDependency,
    database: DatabaseDependency,
) -> Any:
    """List synchronization runs for a connection."""
    async with database.session_factory() as session:
        # Verify connection exists and belongs to tenant
        conn_stmt = select(SourceConnectionRow).where(
            SourceConnectionRow.id == connection_id,
            SourceConnectionRow.tenant_id == str(actor.tenant_id),
        )
        conn_result = await session.execute(conn_stmt)
        if not conn_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Connection not found")
        
        # Get runs
        stmt = select(SyncRunRow).where(
            SyncRunRow.connection_id == connection_id,
            SyncRunRow.tenant_id == str(actor.tenant_id),
        ).order_by(SyncRunRow.started_at.desc()).limit(20)
        
        result = await session.execute(stmt)
        runs = result.scalars().all()
        
        return [
            SyncRunResponse(
                id=run.id,
                tenant_id=run.tenant_id,
                connection_id=run.connection_id,
                run_mode=run.run_mode,
                status=run.status,
                started_at=run.started_at,
                completed_at=run.completed_at,
                cursor_before=run.cursor_before,
                cursor_after=run.cursor_after,
                records_read=run.records_read,
                records_created=run.records_created,
                records_updated=run.records_updated,
                records_failed=run.records_failed,
                error_summary=run.error_summary,
            )
            for run in runs
        ]


@router.get("/connections/{connection_id}/errors", response_model=list[SyncErrorResponse])
async def list_sync_errors(
    connection_id: str,
    actor: ActorDependency,
    database: DatabaseDependency,
    resolved: bool | None = None,
) -> Any:
    """List synchronization errors for a connection."""
    async with database.session_factory() as session:
        # Verify connection
        conn_stmt = select(SourceConnectionRow).where(
            SourceConnectionRow.id == connection_id,
            SourceConnectionRow.tenant_id == str(actor.tenant_id),
        )
        conn_result = await session.execute(conn_stmt)
        if not conn_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Connection not found")
        
        # Get errors
        stmt = select(SyncErrorRow).where(
            SyncErrorRow.connection_id == connection_id,
            SyncErrorRow.tenant_id == str(actor.tenant_id),
        )
        
        if resolved is False:
            stmt = stmt.where(SyncErrorRow.resolved_at.is_(None))
        elif resolved is True:
            stmt = stmt.where(SyncErrorRow.resolved_at.isnot(None))
        
        stmt = stmt.order_by(SyncErrorRow.created_at.desc()).limit(100)
        
        result = await session.execute(stmt)
        errors = result.scalars().all()
        
        return [
            SyncErrorResponse(
                id=err.id,
                sync_run_id=err.sync_run_id,
                connection_id=err.connection_id,
                external_id=err.external_id,
                error_code=err.error_code,
                error_message=err.error_message,
                field_name=err.field_name,
                record_snapshot=err.record_snapshot,
                retry_count=err.retry_count,
                created_at=err.created_at,
                resolved_at=err.resolved_at,
            )
            for err in errors
        ]
