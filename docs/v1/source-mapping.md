# V1 示范来源字段映射

## 概述

本文档说明示范商品库和素材库的字段映射关系，以及如何将来源数据转换为 CloudCtl 内部规范格式。

## 商品库字段映射

### 来源 → 内部模型

| 来源字段 | 内部字段 | 类型转换 | 验证规则 | 备注 |
|---------|---------|---------|---------|------|
| `product_id` | `Product.external_id` | string → string | 必填，唯一 | 来源稳定标识 |
| `title` | `Product.title` | string → string | 必填，1-60字符 | 闲鱼限制30字，需截断 |
| `description` | `Product.description` | string → string | 必填，≤3000字符 | 保留换行符 |
| `price` | `Product.price_amount` | decimal → Decimal | 必填，≥0.01 | 精确到分，不使用浮点 |
| - | `Product.price_currency` | - → 'CNY' | 固定值 | 人民币 |
| `stock` | `Product.stock_quantity` | int → int | 可选，≥0 | 首版不自动扣减 |
| `category` | `Product.metadata.category` | string → string | 可选 | 平台覆盖时映射到具体类目 |
| `condition` | `Product.metadata.condition` | string → string | 可选，枚举 | 闲鱼：全新/99新/95新/9成新 |
| `media_refs` | `Product.media_refs` | csv → list[str] | 可选 | 分号或逗号分隔 |
| `updated_at` | `SourceRecordLink.source_version` | timestamp → datetime | 必填 | 增量同步游标 |

### 平台特定覆盖

#### 闲鱼（Xianyu）

| 平台字段 | 来源 | 映射规则 |
|---------|------|---------|
| `title` | `Product.title` | 截断到30字符，保留完整词 |
| `price` | `Product.price_amount` | 转为字符串，保留两位小数 |
| `desc` | `Product.description` | 原样，最多3000字符 |
| `stuff_status` | `Product.metadata.condition` | 映射：全新→1, 99新→2, 95新→3, 9成新→4 |
| `cate_id` | 平台覆盖 | 用户手动选择或规则映射 |
| `location` | 平台覆盖 | 发货地，用户配置 |
| `images` | `Product.media_refs` | 按顺序，最多9张 |

#### 小红书（Xiaohongshu）

| 平台字段 | 来源 | 映射规则 |
|---------|------|---------|
| `title` | `Product.title` | 限制20字符 |
| `desc` | `Product.description` | 限制1000字符，支持话题标签 |
| `images` | `Product.media_refs` | 最多18张，建议9张 |
| `location` | 平台覆盖 | 可选，地理位置 |

## 素材库字段映射

### 来源 → 内部模型

| 来源字段 | 内部字段 | 类型转换 | 验证规则 | 备注 |
|---------|---------|---------|---------|------|
| `file_name` | `MediaAsset.external_id` | string → string | 必填，唯一 | 文件名作为稳定标识 |
| `file_path` | 读取路径 | string → path | 必填 | 相对于 base_path |
| `content_type` | `MediaAsset.content_type` | string → string | 必填，MIME | image/jpeg, image/png, video/mp4 |
| `size_bytes` | `MediaAsset.size_bytes` | int → int | 必填，>0 | 原文件大小 |
| `sha256` | `MediaAsset.sha256` | string → string | 必填，64字符 | 内容哈希，幂等标识 |
| `width` | `MediaAsset.metadata.width` | int → int | 可选 | 图片/视频宽度 |
| `height` | `MediaAsset.metadata.height` | int → int | 可选 | 图片/视频高度 |
| `file_mtime` | `SourceRecordLink.source_version` | timestamp → datetime | 必填 | 文件修改时间 |

### 平台约束

| 平台 | 图片数量 | 图片格式 | 图片大小 | 视频格式 | 视频大小 |
|------|---------|---------|---------|---------|---------|
| 闲鱼 | 1-9张 | JPG, PNG | ≤10MB/张 | 不支持 | - |
| 小红书 | 1-18张 | JPG, PNG | ≤20MB/张 | MP4 | ≤1GB, ≤5分钟 |
| 抖音 | - | - | - | MP4 | ≤4GB, 15秒-10分钟 |
| 微信公众号 | ≤10张 | JPG, PNG | ≤10MB/张 | MP4 | ≤100MB |

## 数据转换流程

### 1. 商品同步流程

```python
def sync_product(row: dict) -> ProductRow:
    # 1. 验证必填字段
    validate_required(['product_id', 'title', 'description', 'price', 'updated_at'], row)
    
    # 2. 类型转换
    price_amount = Decimal(row['price'])
    if price_amount < Decimal('0.01'):
        raise ValueError("price must be >= 0.01")
    
    # 3. 媒体引用解析
    media_refs = []
    if row.get('media_refs'):
        media_refs = [ref.strip() for ref in row['media_refs'].replace(';', ',').split(',') if ref.strip()]
    
    # 4. 创建或更新 Product
    product = upsert_product(
        external_id=row['product_id'],
        source_connection_id=connection_id,
        title=row['title'],
        description=row['description'],
        price_amount=price_amount,
        price_currency='CNY',
        stock_quantity=int(row['stock']) if row.get('stock') else None,
        metadata={
            'category': row.get('category'),
            'condition': row.get('condition'),
        },
        media_refs=media_refs,
    )
    
    # 5. 记录 SourceRecordLink
    record_source_link(
        connection_id=connection_id,
        entity_kind='product',
        external_id=row['product_id'],
        internal_id=product.id,
        source_version=parse_timestamp(row['updated_at']),
        source_hash=compute_hash(row),
    )
    
    return product
```

### 2. 素材同步流程

```python
def sync_media(row: dict, base_path: Path) -> MediaAssetRow:
    # 1. 验证必填字段
    validate_required(['file_name', 'file_path', 'content_type', 'size_bytes', 'sha256'], row)
    
    # 2. 读取原文件
    file_full_path = base_path / row['file_path']
    if not file_full_path.exists():
        raise FileNotFoundError(f"Media file not found: {file_full_path}")
    
    file_content = file_full_path.read_bytes()
    actual_sha256 = hashlib.sha256(file_content).hexdigest()
    
    # 3. 验证哈希
    if actual_sha256 != row['sha256']:
        raise ValueError(f"SHA256 mismatch for {row['file_name']}")
    
    # 4. 上传到 S3
    object_key = f"media/{tenant_id}/{actual_sha256[:2]}/{actual_sha256}"
    s3_client.put_object(Bucket=bucket, Key=object_key, Body=file_content)
    
    # 5. 注册 MediaAsset
    asset = upsert_media_asset(
        external_id=row['file_name'],
        source_connection_id=connection_id,
        sha256=actual_sha256,
        object_key=object_key,
        content_type=row['content_type'],
        size_bytes=int(row['size_bytes']),
        metadata={
            'file_name': row['file_name'],
            'width': int(row['width']) if row.get('width') else None,
            'height': int(row['height']) if row.get('height') else None,
        },
    )
    
    # 6. 记录 SourceRecordLink
    record_source_link(
        connection_id=connection_id,
        entity_kind='media',
        external_id=row['file_name'],
        internal_id=asset.id,
        source_version=parse_timestamp(row['file_mtime']),
        source_hash=actual_sha256,
    )
    
    return asset
```

## 冲突处理

### 来源字段冲突
- **策略**: 来源优先（source_priority）
- **规则**: 来源字段更新时，覆盖 CloudCtl 内部值
- **例外**: 平台覆盖字段（category, condition）保存在 `platform_overrides` 中，不被来源更新覆盖

### 重复同步
- **幂等保证**: 使用 `source_hash` 判断内容是否变化
- **规则**: 相同 external_id + 相同 source_hash → 不创建新 revision
- **版本追踪**: source_version 用于增量同步游标

### 删除处理
- **软删除**: 来源记录删除时，标记 `SourceRecordLink.deleted_at`
- **媒体保留**: 已被 PublishSnapshot 引用的媒体不物理删除
- **回写**: 首版默认不反向删除来源记录

## 验证检查清单

### 商品数据验证
- [ ] product_id 唯一且稳定
- [ ] title 长度符合各平台限制
- [ ] price 使用 Decimal，精确到分
- [ ] price 货币单位明确为 CNY
- [ ] description 不包含敏感信息
- [ ] media_refs 引用的素材都存在
- [ ] updated_at 格式正确且可解析

### 素材数据验证
- [ ] 文件实际存在且可读
- [ ] SHA256 哈希与文件内容一致
- [ ] content_type 与文件实际格式匹配
- [ ] size_bytes 与文件实际大小一致
- [ ] 图片尺寸在各平台限制内
- [ ] 文件名不包含特殊字符

### 关联关系验证
- [ ] Product.media_refs 中的 ID 都能找到对应 MediaAsset
- [ ] 每个 Product 至少有 1 张图片（闲鱼、小红书要求）
- [ ] 图片顺序与用户期望一致

## 示范数据统计

### 商品库
- 总记录数: 10
- 类目分布: 手机数码(4), 家用电器(2), 服饰鞋包(2), 个护化妆(2), 家具家居(1)
- 成色分布: 全新(3), 99新(2), 95新(3), 9成新(2)
- 价格范围: ¥149.00 - ¥4,299.00
- 含媒体商品: 9/10

### 素材库
- 总记录数: 20
- 格式分布: JPEG(20)
- 总大小: ~15 MB
- 尺寸分布: 1080x1080(3), 1080x1440(4), 1080x1920(6), 1920x1080(5), 1920x1440(2), 3840x2160(1)

### 关联关系
- 平均每商品媒体数: 2.2 张
- 最多媒体商品: P001, P007 (3张)
- 无媒体商品: P010 (1个)
