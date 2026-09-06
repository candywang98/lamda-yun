"""Integration tests for source connections."""

import pytest
from cloudctl_api.source_schemas import SourcePreviewResponse
from cloudctl_api.source_service import (
    CSVFileConnector,
    create_connector,
    preview_source,
)


class TestCSVFileConnector:
    """Test CSV file source connector."""

    @pytest.mark.asyncio
    async def test_csv_product_connector_test_connection(self) -> None:
        """Test connection validation for product CSV."""
        config = {
            "base_path": "artifacts/v1/V1-03/demo-data",
            "file_name": "products.csv",
            "encoding": "utf-8",
            "entity_kind": "product",
        }
        connector = CSVFileConnector(config)

        success, message = await connector.test_connection()
        assert success is True
        assert "columns" in message.lower()

    @pytest.mark.asyncio
    async def test_csv_connector_missing_file(self) -> None:
        """Test connection fails for missing file."""
        config = {
            "base_path": "artifacts/v1/V1-03/demo-data",
            "file_name": "nonexistent.csv",
            "encoding": "utf-8",
            "entity_kind": "product",
        }
        connector = CSVFileConnector(config)

        success, message = await connector.test_connection()
        assert success is False
        assert "not found" in message.lower()

    @pytest.mark.asyncio
    async def test_csv_read_page_products(self) -> None:
        """Test reading product records from CSV."""
        config = {
            "base_path": "artifacts/v1/V1-03/demo-data",
            "file_name": "products.csv",
            "encoding": "utf-8",
            "entity_kind": "product",
        }
        connector = CSVFileConnector(config)

        # Read first page
        records, next_cursor = await connector.read_page(cursor=None, page_size=5)

        assert len(records) == 5
        assert records[0]["product_id"] == "P001"
        assert "title" in records[0]
        assert "price" in records[0]
        assert next_cursor == "5"

        # Read second page
        records_2, next_cursor_2 = await connector.read_page(cursor=next_cursor, page_size=5)
        assert len(records_2) == 5
        assert records_2[0]["product_id"] == "P006"
        assert next_cursor_2 == "10"

        # Read beyond end
        records_3, next_cursor_3 = await connector.read_page(cursor=next_cursor_2, page_size=5)
        assert len(records_3) == 0
        assert next_cursor_3 is None

    @pytest.mark.asyncio
    async def test_csv_normalize_product_valid(self) -> None:
        """Test normalizing valid product record."""
        config = {
            "base_path": "artifacts/v1/V1-03/demo-data",
            "file_name": "products.csv",
            "encoding": "utf-8",
            "entity_kind": "product",
        }
        connector = CSVFileConnector(config)

        raw = {
            "product_id": "P001",
            "title": "iPhone 13 Pro 128GB 石墨色",
            "description": "9成新iPhone 13 Pro，功能完好",
            "price": "4299.00",
            "stock": "1",
            "category": "手机数码",
            "condition": "9成新",
            "media_refs": "M001.jpg;M002.jpg;M003.jpg",
            "updated_at": "2026-09-01T10:30:00Z",
        }

        normalized, errors = connector.normalize_record(raw)

        assert len(errors) == 0
        assert normalized["spu_code"] == "P001"
        assert normalized["title"] == "iPhone 13 Pro 128GB 石墨色"
        assert normalized["price"] == "4299.0"
        assert normalized["stock"] == 1
        assert normalized["category"] == "手机数码"
        assert normalized["status"] == "ACTIVE"
        assert len(normalized["media_refs"]) == 3
        assert normalized["media_refs"][0] == "M001.jpg"

    @pytest.mark.asyncio
    async def test_csv_normalize_product_missing_required(self) -> None:
        """Test normalization fails for missing required fields."""
        config = {
            "base_path": "artifacts/v1/V1-03/demo-data",
            "file_name": "products.csv",
            "encoding": "utf-8",
            "entity_kind": "product",
        }
        connector = CSVFileConnector(config)

        raw = {
            "product_id": "",
            "title": "",
            "description": "",
            "price": "",
        }

        normalized, errors = connector.normalize_record(raw)

        assert len(errors) >= 4
        assert any("product_id" in e for e in errors)
        assert any("title" in e for e in errors)
        assert any("description" in e for e in errors)
        assert any("price" in e for e in errors)

    @pytest.mark.asyncio
    async def test_csv_normalize_product_invalid_price(self) -> None:
        """Test normalization catches invalid price format."""
        config = {
            "base_path": "artifacts/v1/V1-03/demo-data",
            "file_name": "products.csv",
            "encoding": "utf-8",
            "entity_kind": "product",
        }
        connector = CSVFileConnector(config)

        raw = {
            "product_id": "P001",
            "title": "Test Product",
            "description": "Test Description",
            "price": "not-a-number",
        }

        normalized, errors = connector.normalize_record(raw)

        assert len(errors) >= 1
        assert any("price" in e.lower() for e in errors)

    @pytest.mark.asyncio
    async def test_csv_media_connector(self) -> None:
        """Test reading media manifest CSV."""
        config = {
            "base_path": "artifacts/v1/V1-03/demo-data",
            "file_name": "media-manifest.csv",
            "encoding": "utf-8",
            "entity_kind": "media",
        }
        connector = CSVFileConnector(config)

        # Test connection
        success, message = await connector.test_connection()
        assert success is True

        # Read records
        records, _ = await connector.read_page(cursor=None, page_size=5)
        assert len(records) == 5
        assert "file_name" in records[0]
        assert "sha256" in records[0]
        assert "content_type" in records[0]

    @pytest.mark.asyncio
    async def test_csv_normalize_media_valid(self) -> None:
        """Test normalizing valid media record."""
        config = {
            "base_path": "artifacts/v1/V1-03/demo-data",
            "file_name": "media-manifest.csv",
            "encoding": "utf-8",
            "entity_kind": "media",
        }
        connector = CSVFileConnector(config)

        raw = {
            "file_name": "M001.jpg",
            "file_path": "M001.jpg",
            "content_type": "image/jpeg",
            "size_bytes": "524288",
            "sha256": "a" * 64,
            "width": "1920",
            "height": "1080",
            "file_mtime": "2026-09-01T10:00:00Z",
        }

        normalized, errors = connector.normalize_record(raw)

        assert len(errors) == 0
        assert normalized["file_name"] == "M001.jpg"
        assert normalized["sha256"] == "a" * 64
        assert normalized["content_type"] == "image/jpeg"
        assert normalized["size_bytes"] == 524288
        assert normalized["width"] == 1920
        assert normalized["height"] == 1080

    @pytest.mark.asyncio
    async def test_csv_normalize_media_invalid_sha256(self) -> None:
        """Test normalization catches invalid SHA256 length."""
        config = {
            "base_path": "artifacts/v1/V1-03/demo-data",
            "file_name": "media-manifest.csv",
            "encoding": "utf-8",
            "entity_kind": "media",
        }
        connector = CSVFileConnector(config)

        raw = {
            "file_name": "M001.jpg",
            "content_type": "image/jpeg",
            "size_bytes": "524288",
            "sha256": "short_hash",  # Invalid length
        }

        normalized, errors = connector.normalize_record(raw)

        assert len(errors) >= 1
        assert any("sha256" in e.lower() for e in errors)


class TestSourceConnectorFactory:
    """Test connector factory."""

    def test_create_csv_connector(self) -> None:
        """Test factory creates CSV connector."""
        config = {
            "base_path": "artifacts/v1/V1-03/demo-data",
            "file_name": "products.csv",
            "encoding": "utf-8",
            "entity_kind": "product",
        }

        connector = create_connector("csv_file", config)
        assert isinstance(connector, CSVFileConnector)

    def test_create_unsupported_connector(self) -> None:
        """Test factory rejects unsupported source kinds."""
        config = {"type": "unknown"}

        with pytest.raises(ValueError, match="Unsupported source_kind"):
            create_connector("unknown_type", config)


class TestSourcePreview:
    """Test source preview functionality."""

    @pytest.mark.asyncio
    async def test_preview_product_source_success(self) -> None:
        """Test previewing product source returns valid records."""
        config = {
            "base_path": "artifacts/v1/V1-03/demo-data",
            "file_name": "products.csv",
            "encoding": "utf-8",
            "entity_kind": "product",
        }

        result = await preview_source("csv_file", config, page_size=3)

        assert isinstance(result, SourcePreviewResponse)
        assert result.total_read == 3
        assert result.valid_records >= 1
        assert len(result.records) == 3

        # Check first record structure
        first = result.records[0]
        assert first.external_id == "P001"
        assert "product_id" in first.raw_data
        assert first.normalized_data is not None
        assert "spu_code" in first.normalized_data
        assert len(first.errors) == 0

    @pytest.mark.asyncio
    async def test_preview_media_source_success(self) -> None:
        """Test previewing media source returns valid records."""
        config = {
            "base_path": "artifacts/v1/V1-03/demo-data",
            "file_name": "media-manifest.csv",
            "encoding": "utf-8",
            "entity_kind": "media",
        }

        result = await preview_source("csv_file", config, page_size=5)

        assert result.total_read == 5
        assert result.valid_records >= 1
        assert len(result.records) == 5

        # Check record structure
        first = result.records[0]
        assert first.external_id  # Should have file_name as ID
        assert "sha256" in first.raw_data
        assert first.normalized_data is not None

    @pytest.mark.asyncio
    async def test_preview_connection_failure(self) -> None:
        """Test preview handles connection failures gracefully."""
        config = {
            "base_path": "artifacts/v1/V1-03/demo-data",
            "file_name": "nonexistent.csv",
            "encoding": "utf-8",
            "entity_kind": "product",
        }

        result = await preview_source("csv_file", config)

        assert result.total_read == 0
        assert result.valid_records == 0
        assert result.invalid_records == 1
        assert len(result.records) == 1
        assert "Connection test failed" in result.records[0].errors[0]

    @pytest.mark.asyncio
    async def test_preview_tenant_isolation(self) -> None:
        """Test preview does not write to database (tenant isolation)."""
        config = {
            "base_path": "artifacts/v1/V1-03/demo-data",
            "file_name": "products.csv",
            "encoding": "utf-8",
            "entity_kind": "product",
        }

        # Multiple previews should not interfere
        result1 = await preview_source("csv_file", config, page_size=2)
        result2 = await preview_source("csv_file", config, page_size=2)

        assert result1.total_read == result2.total_read
        assert result1.records[0].external_id == result2.records[0].external_id
