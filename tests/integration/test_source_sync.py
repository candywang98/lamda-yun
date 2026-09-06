"""Integration tests for source synchronization."""

from datetime import UTC, datetime

import pytest
from cloudctl_api.db import (
    ProductRow,
    SourceConnectionRow,
    SourceRecordLinkRow,
    SyncErrorRow,
    SyncRunRow,
)
from cloudctl_api.media_store import InMemoryObjectStore
from cloudctl_api.source_service import CSVFileConnector, execute_sync_run
from sqlalchemy import select


class TestSourceSync:
    """Test source synchronization with database writes."""

    @pytest.mark.asyncio
    async def test_sync_product_first_run(self, session, tenant_id: str, user_id: str) -> None:
        """Test first synchronization creates products."""
        from datetime import UTC, datetime
        
        # Create connection
        connection = SourceConnectionRow(
            id="conn-1",
            tenant_id=tenant_id,
            connection_name="demo-products",
            source_kind="csv_file",
            entity_kind="product",
            config={
                "base_path": "artifacts/v1/V1-03/demo-data",
                "file_name": "products.csv",
                "encoding": "utf-8",
                "entity_kind": "product",
            },
            mapping_version="1.0",
            status="active",
            created_by=user_id,
            created_at=datetime.now(UTC),
        )
        session.add(connection)
        await session.flush()

        # Create connector
        connector = CSVFileConnector(connection.config)
        object_store = InMemoryObjectStore()

        # Execute sync
        result = await execute_sync_run(
            session=session,
            connection_id=connection.id,
            tenant_id=tenant_id,
            triggered_by=user_id,
            connector=connector,
            object_store=object_store,
            run_mode="full",
            page_size=5,
        )

        print("\n=== Sync Result ===")
        print(f"Status: {result['status']}")
        print(f"Read: {result['records_read']}")
        print(f"Created: {result['records_created']}")
        print(f"Updated: {result['records_updated']}")
        print(f"Failed: {result['records_failed']}")

        # Check errors if any
        if result['records_failed'] > 0:
            error_stmt = select(SyncErrorRow).where(
                SyncErrorRow.sync_run_id == result["sync_run_id"]
            )
            error_result = await session.execute(error_stmt)
            errors = error_result.scalars().all()
            print(f"\n=== Errors ({len(errors)}) ===")
            for err in errors[:3]:  # Show first 3
                print(f"- {err.external_id}: {err.error_message}")

        assert result["status"] == "completed"
        assert result["records_read"] == 10  # All demo products
        assert result["records_created"] == 10
        assert result["records_updated"] == 0
        assert result["records_failed"] == 0

        # Verify sync run record
        stmt = select(SyncRunRow).where(SyncRunRow.id == result["sync_run_id"])
        sync_result = await session.execute(stmt)
        sync_run = sync_result.scalar_one()
        
        assert sync_run.status == "completed"
        assert sync_run.records_read == 10
        assert sync_run.records_created == 10

        # Verify products created
        prod_stmt = select(ProductRow).where(ProductRow.tenant_id == tenant_id)
        prod_result = await session.execute(prod_stmt)
        products = prod_result.scalars().all()
        
        assert len(products) == 10
        assert products[0].spu_code == "P001"
        assert "iPhone" in products[0].title
        assert products[0].price == "4299.0"

        # Verify links created
        link_stmt = select(SourceRecordLinkRow).where(
            SourceRecordLinkRow.tenant_id == tenant_id
        )
        link_result = await session.execute(link_stmt)
        links = link_result.scalars().all()
        
        assert len(links) == 10
        assert links[0].external_id == "P001"
        assert links[0].entity_kind == "product"
        assert links[0].tombstoned_at is None

    @pytest.mark.asyncio
    async def test_sync_product_idempotent(self, session, tenant_id: str, user_id: str) -> None:
        """Test repeated sync with same data is idempotent."""
        # Setup connection
        connection = SourceConnectionRow(
            id="conn-2",
            tenant_id=tenant_id,
            connection_name="demo-products-2",
            source_kind="csv_file",
            entity_kind="product",
            config={
                "base_path": "artifacts/v1/V1-03/demo-data",
                "file_name": "products.csv",
                "encoding": "utf-8",
                "entity_kind": "product",
            },
            mapping_version="1.0",
            status="active",
            created_by=user_id,
            created_at=datetime.now(UTC),
        )
        session.add(connection)
        await session.flush()

        connector = CSVFileConnector(connection.config)
        object_store = InMemoryObjectStore()

        # First sync
        result1 = await execute_sync_run(
            session=session,
            connection_id=connection.id,
            tenant_id=tenant_id,
            triggered_by=user_id,
            connector=connector,
            object_store=object_store,
            run_mode="full",
            page_size=100,
        )

        assert result1["records_created"] == 10

        # Second sync with same data
        result2 = await execute_sync_run(
            session=session,
            connection_id=connection.id,
            tenant_id=tenant_id,
            triggered_by=user_id,
            connector=connector,
            object_store=object_store,
            run_mode="incremental",
            page_size=100,
        )

        # Should skip all (same hash)
        assert result2["records_read"] == 10
        assert result2["records_created"] == 0
        assert result2["records_updated"] == 0

        # Still only 10 products
        prod_stmt = select(ProductRow).where(ProductRow.tenant_id == tenant_id)
        prod_result = await session.execute(prod_stmt)
        products = prod_result.scalars().all()
        assert len(products) == 10

    @pytest.mark.asyncio
    async def test_sync_product_update_detection(
        self, session, tenant_id: str, user_id: str, tmp_path
    ) -> None:
        """Test detecting and applying updates."""
        import shutil
        from pathlib import Path

        # Copy demo data to temp directory
        demo_dir = Path("artifacts/v1/V1-03/demo-data")
        temp_dir = tmp_path / "data"
        temp_dir.mkdir()
        shutil.copy(demo_dir / "products.csv", temp_dir / "products.csv")

        # Create connection
        connection = SourceConnectionRow(
            id="conn-3",
            tenant_id=tenant_id,
            connection_name="demo-products-3",
            source_kind="csv_file",
            entity_kind="product",
            config={
                "base_path": str(temp_dir),
                "file_name": "products.csv",
                "encoding": "utf-8",
                "entity_kind": "product",
            },
            mapping_version="1.0",
            status="active",
            created_by=user_id,
            created_at=datetime.now(UTC),
        )
        session.add(connection)
        await session.flush()

        connector = CSVFileConnector(connection.config)
        object_store = InMemoryObjectStore()

        # First sync
        await execute_sync_run(
            session=session,
            connection_id=connection.id,
            tenant_id=tenant_id,
            triggered_by=user_id,
            connector=connector,
            object_store=object_store,
            run_mode="full",
            page_size=100,
        )

        # Modify CSV (change price of P001)
        csv_path = temp_dir / "products.csv"
        content = csv_path.read_text()
        modified = content.replace("4299.00,1,", "3999.00,1,")  # Lower price
        csv_path.write_text(modified)

        # Recreate connector with new data
        connector = CSVFileConnector(connection.config)

        # Second sync
        result2 = await execute_sync_run(
            session=session,
            connection_id=connection.id,
            tenant_id=tenant_id,
            triggered_by=user_id,
            connector=connector,
            object_store=object_store,
            run_mode="incremental",
            page_size=100,
        )

        assert result2["records_updated"] == 1
        assert result2["records_created"] == 0

        # Verify price updated
        prod_stmt = select(ProductRow).where(
            ProductRow.tenant_id == tenant_id, ProductRow.spu_code == "P001"
        )
        prod_result = await session.execute(prod_stmt)
        product = prod_result.scalar_one()
        
        assert product.price == "3999.0"
        assert product.revision == 2

    @pytest.mark.asyncio
    async def test_sync_media_with_download(
        self, session, tenant_id: str, user_id: str
    ) -> None:
        """Test media synchronization with asset download.
        
        Note: Demo media files don't actually exist in artifacts/v1/V1-03/demo-data/media/,
        so this test expects failures for missing files.
        """
        # Create connection
        connection = SourceConnectionRow(
            id="conn-4",
            tenant_id=tenant_id,
            connection_name="demo-media",
            source_kind="csv_file",
            entity_kind="media",
            config={
                "base_path": "artifacts/v1/V1-03/demo-data",
                "file_name": "media-manifest.csv",
                "encoding": "utf-8",
                "entity_kind": "media",
            },
            mapping_version="1.0",
            status="active",
            created_by=user_id,
            created_at=datetime.now(UTC),
        )
        session.add(connection)
        await session.flush()

        connector = CSVFileConnector(connection.config)
        object_store = InMemoryObjectStore()

        # Execute sync
        result = await execute_sync_run(
            session=session,
            connection_id=connection.id,
            tenant_id=tenant_id,
            triggered_by=user_id,
            connector=connector,
            object_store=object_store,
            run_mode="full",
            page_size=5,
        )

        assert result["status"] == "completed"
        assert result["records_read"] == 20  # All demo media
        # Since actual media files don't exist, all should fail
        assert result["records_created"] == 0
        assert result["records_failed"] == 20

        # Verify errors recorded
        error_stmt = select(SyncErrorRow).where(
            SyncErrorRow.connection_id == connection.id
        )
        error_result = await session.execute(error_stmt)
        errors = error_result.scalars().all()
        
        assert len(errors) == 20
        assert all("not found" in e.error_message.lower() for e in errors)

    @pytest.mark.asyncio
    async def test_sync_validation_errors(
        self, session, tenant_id: str, user_id: str, tmp_path
    ) -> None:
        """Test validation errors are recorded."""
        # Create invalid CSV
        csv_path = tmp_path / "invalid.csv"
        csv_path.write_text(
            "product_id,title,description,price,stock\n"
            ",Missing ID,Description,100.00,1\n"
            "P999,Valid Product,Description,invalid-price,1\n"
        )

        connection = SourceConnectionRow(
            id="conn-5",
            tenant_id=tenant_id,
            connection_name="invalid-products",
            source_kind="csv_file",
            entity_kind="product",
            config={
                "base_path": str(tmp_path),
                "file_name": "invalid.csv",
                "encoding": "utf-8",
                "entity_kind": "product",
            },
            mapping_version="1.0",
            status="active",
            created_by=user_id,
            created_at=datetime.now(UTC),
        )
        session.add(connection)
        await session.flush()

        connector = CSVFileConnector(connection.config)
        object_store = InMemoryObjectStore()

        # Execute sync
        result = await execute_sync_run(
            session=session,
            connection_id=connection.id,
            tenant_id=tenant_id,
            triggered_by=user_id,
            connector=connector,
            object_store=object_store,
            run_mode="full",
            page_size=100,
        )

        assert result["records_read"] == 2
        assert result["records_failed"] == 2
        assert result["records_created"] == 0

        # Verify errors recorded
        error_stmt = select(SyncErrorRow).where(
            SyncErrorRow.connection_id == connection.id
        )
        error_result = await session.execute(error_stmt)
        errors = error_result.scalars().all()
        
        assert len(errors) >= 2
        assert any("product_id" in e.error_message for e in errors)
        assert any("price" in e.error_message.lower() for e in errors)

    @pytest.mark.asyncio
    async def test_sync_cursor_persistence(
        self, session, tenant_id: str, user_id: str
    ) -> None:
        """Test cursor is persisted across pages."""
        connection = SourceConnectionRow(
            id="conn-6",
            tenant_id=tenant_id,
            connection_name="cursor-test",
            source_kind="csv_file",
            entity_kind="product",
            config={
                "base_path": "artifacts/v1/V1-03/demo-data",
                "file_name": "products.csv",
                "encoding": "utf-8",
                "entity_kind": "product",
            },
            mapping_version="1.0",
            status="active",
            created_by=user_id,
            created_at=datetime.now(UTC),
        )
        session.add(connection)
        await session.flush()

        connector = CSVFileConnector(connection.config)
        object_store = InMemoryObjectStore()

        # Sync with small page size
        result = await execute_sync_run(
            session=session,
            connection_id=connection.id,
            tenant_id=tenant_id,
            triggered_by=user_id,
            connector=connector,
            object_store=object_store,
            run_mode="full",
            page_size=3,  # Small pages
        )

        assert result["records_read"] == 10

        # Check sync run has final cursor
        stmt = select(SyncRunRow).where(SyncRunRow.id == result["sync_run_id"])
        sync_result = await session.execute(stmt)
        sync_run = sync_result.scalar_one()
        
        # Cursor should be None (end of data)
        assert sync_run.cursor_after is None
        assert sync_run.cursor_before is None  # First run


@pytest.fixture
async def tenant_id(session) -> str:
    """Create test tenant."""
    from datetime import UTC, datetime
    
    from cloudctl_api.db import TenantRow
    
    tenant = TenantRow(
        id="test-tenant-1",
        name="Test Tenant",
        created_at=datetime.now(UTC),
    )
    session.add(tenant)
    await session.flush()
    return tenant.id


@pytest.fixture
async def user_id(session, tenant_id: str) -> str:
    """Create test user."""
    from datetime import UTC, datetime
    
    from cloudctl_api.db import UserRow
    
    user = UserRow(
        id="test-user-1",
        tenant_id=tenant_id,
        oidc_subject="test-subject",
        roles=["admin"],
        disabled=False,
        created_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    return user.id
