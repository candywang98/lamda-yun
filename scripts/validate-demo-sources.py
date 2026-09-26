#!/usr/bin/env python3
"""验证 V1-03 示范商品库和素材库数据完整性"""

import csv
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEMO_DATA = ROOT / "artifacts/v1/V1-03/demo-data"
PROFILE = ROOT / "docs/v1/source-profile.json"


def validate_profile():
    """验证 source-profile.json 结构"""
    print("验证 source-profile.json...")

    if not PROFILE.exists():
        raise FileNotFoundError(f"Profile not found: {PROFILE}")

    with open(PROFILE, encoding="utf-8") as f:
        profile = json.load(f)

    # 必填字段
    assert "version" in profile, "Missing version"
    assert "sources" in profile, "Missing sources"
    assert len(profile["sources"]) >= 2, "Expected at least 2 sources"

    # 验证来源定义
    for source in profile["sources"]:
        assert "id" in source, "Missing source.id"
        assert "kind" in source, "Missing source.kind"
        assert "entity_kind" in source, "Missing source.entity_kind"
        assert "primary_key" in source, "Missing source.primary_key"
        assert "fields" in source, "Missing source.fields"

    print("  ✓ Profile structure valid")
    return profile


def validate_products():
    """验证商品 CSV 数据"""
    print("\n验证商品数据...")

    products_csv = DEMO_DATA / "products.csv"
    if not products_csv.exists():
        raise FileNotFoundError(f"Products CSV not found: {products_csv}")

    with open(products_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) >= 10, f"Expected >= 10 products, got {len(rows)}"

    product_ids = set()
    issues = []

    for idx, row in enumerate(rows, 1):
        # 必填字段
        if not row.get("product_id"):
            issues.append(f"Row {idx}: Missing product_id")
        elif row["product_id"] in product_ids:
            issues.append(f"Row {idx}: Duplicate product_id {row['product_id']}")
        else:
            product_ids.add(row["product_id"])

        if not row.get("title"):
            issues.append(f"Row {idx}: Missing title")
        elif len(row["title"]) > 60:
            issues.append(f"Row {idx}: Title too long ({len(row['title'])} > 60)")

        if not row.get("description"):
            issues.append(f"Row {idx}: Missing description")
        elif len(row["description"]) > 3000:
            issues.append(f"Row {idx}: Description too long")

        # 价格验证
        if not row.get("price"):
            issues.append(f"Row {idx}: Missing price")
        else:
            try:
                price = Decimal(row["price"])
                if price < Decimal("0.01"):
                    issues.append(f"Row {idx}: Price too low: {price}")
            except (InvalidOperation, ValueError):
                issues.append(f"Row {idx}: Invalid price format: {row['price']}")

        # 时间戳验证
        if not row.get("updated_at"):
            issues.append(f"Row {idx}: Missing updated_at")
        else:
            try:
                datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
            except ValueError:
                issues.append(f"Row {idx}: Invalid timestamp: {row['updated_at']}")

    if issues:
        for issue in issues:
            print(f"  ✗ {issue}")
        raise ValueError(f"Found {len(issues)} validation errors in products")

    print(f"  ✓ {len(rows)} products validated")
    print(
        f"  ✓ Price range: {min(Decimal(r['price']) for r in rows)} - "
        f"{max(Decimal(r['price']) for r in rows)} CNY"
    )

    return rows


def validate_media():
    """验证素材清单数据"""
    print("\n验证素材清单...")

    media_csv = DEMO_DATA / "media-manifest.csv"
    if not media_csv.exists():
        raise FileNotFoundError(f"Media manifest not found: {media_csv}")

    with open(media_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) >= 20, f"Expected >= 20 media files, got {len(rows)}"

    file_names = set()
    sha256_hashes = set()
    issues = []
    total_size = 0

    for idx, row in enumerate(rows, 1):
        # 必填字段
        if not row.get("file_name"):
            issues.append(f"Row {idx}: Missing file_name")
        elif row["file_name"] in file_names:
            issues.append(f"Row {idx}: Duplicate file_name {row['file_name']}")
        else:
            file_names.add(row["file_name"])

        if not row.get("sha256"):
            issues.append(f"Row {idx}: Missing sha256")
        elif len(row["sha256"]) != 64:
            issues.append(f"Row {idx}: Invalid sha256 length: {len(row['sha256'])}")
        else:
            sha256_hashes.add(row["sha256"])

        if not row.get("content_type"):
            issues.append(f"Row {idx}: Missing content_type")
        elif row["content_type"] not in ["image/jpeg", "image/png", "video/mp4"]:
            issues.append(f"Row {idx}: Unsupported content_type: {row['content_type']}")

        # 大小验证
        if not row.get("size_bytes"):
            issues.append(f"Row {idx}: Missing size_bytes")
        else:
            try:
                size = int(row["size_bytes"])
                if size <= 0:
                    issues.append(f"Row {idx}: Invalid size: {size}")
                else:
                    total_size += size
            except ValueError:
                issues.append(f"Row {idx}: Invalid size_bytes: {row['size_bytes']}")

        # 尺寸验证（可选）
        if row.get("width"):
            try:
                width = int(row["width"])
                if width <= 0:
                    issues.append(f"Row {idx}: Invalid width: {width}")
            except ValueError:
                issues.append(f"Row {idx}: Invalid width format: {row['width']}")

        if row.get("height"):
            try:
                height = int(row["height"])
                if height <= 0:
                    issues.append(f"Row {idx}: Invalid height: {height}")
            except ValueError:
                issues.append(f"Row {idx}: Invalid height format: {row['height']}")

    if issues:
        for issue in issues:
            print(f"  ✗ {issue}")
        raise ValueError(f"Found {len(issues)} validation errors in media")

    print(f"  ✓ {len(rows)} media files validated")
    print(f"  ✓ Total size: {total_size:,} bytes (~{total_size / (1024 * 1024):.1f} MB)")
    print(f"  ✓ Unique SHA256 hashes: {len(sha256_hashes)}")

    return rows


def validate_relationships(products: list[dict[str, Any]], media: list[dict[str, Any]]):
    """验证商品和素材的关联关系"""
    print("\n验证关联关系...")

    media_ids = {row["file_name"] for row in media}
    issues = []

    total_refs = 0
    products_with_media = 0

    for product in products:
        media_refs = product.get("media_refs", "").strip()
        if not media_refs:
            continue

        products_with_media += 1
        refs = [ref.strip() for ref in media_refs.replace(";", ",").split(",") if ref.strip()]
        total_refs += len(refs)

        for ref in refs:
            if ref not in media_ids:
                issues.append(f"Product {product['product_id']}: Referenced media {ref} not found")

    if issues:
        for issue in issues:
            print(f"  ✗ {issue}")
        raise ValueError(f"Found {len(issues)} relationship errors")

    print(f"  ✓ {products_with_media}/{len(products)} products have media")
    print(f"  ✓ {total_refs} total media references")
    print(f"  ✓ Average {total_refs / products_with_media:.1f} media per product (with media)")


def main():
    print("=== V1-03 示范数据验证 ===\n")

    try:
        profile = validate_profile()
        products = validate_products()
        media = validate_media()
        validate_relationships(products, media)

        print("\n" + "=" * 50)
        print("✓ 所有验证通过")
        print("=" * 50)

        # 输出摘要
        print("\n摘要:")
        print(f"  - 商品数: {len(products)}")
        print(f"  - 素材数: {len(media)}")
        print(f"  - 来源类型: {', '.join(s['kind'] for s in profile['sources'])}")
        print(f"  - 认证方式: {profile['security']['credentials_storage']}")

    except Exception as e:
        print(f"\n✗ 验证失败: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
