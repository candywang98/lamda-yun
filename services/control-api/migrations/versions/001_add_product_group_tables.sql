-- Migration: Add ProductGroup and ProductGroupMembership tables
-- Date: 2026-09-06
-- Issue: B001 - 商品分组外键错误修复

-- 创建 product_group 表
CREATE TABLE IF NOT EXISTS product_group (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    name VARCHAR(160) NOT NULL,
    description TEXT,
    created_by VARCHAR(36) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_product_group_tenant_name UNIQUE (tenant_id, name)
);

CREATE INDEX IF NOT EXISTS ix_product_group_tenant_id ON product_group(tenant_id);

-- 创建 product_group_membership 表
CREATE TABLE IF NOT EXISTS product_group_membership (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    group_id VARCHAR(36) NOT NULL,
    product_id VARCHAR(36) NOT NULL,
    added_by VARCHAR(36) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_product_group_membership_group FOREIGN KEY (group_id) REFERENCES product_group(id),
    CONSTRAINT fk_product_group_membership_product FOREIGN KEY (product_id) REFERENCES product(id),
    CONSTRAINT uq_product_group_membership_group_product UNIQUE (group_id, product_id)
);

CREATE INDEX IF NOT EXISTS ix_product_group_membership_tenant_id ON product_group_membership(tenant_id);
CREATE INDEX IF NOT EXISTS ix_product_group_membership_group_id ON product_group_membership(group_id);
CREATE INDEX IF NOT EXISTS ix_product_group_membership_product_id ON product_group_membership(product_id);

-- 注意：不自动迁移数据，因为 ContentGroupMembership 中的 content_id 可能不是有效的 product_id
-- 如果需要迁移数据，请手动执行：
-- INSERT INTO product_group_membership (id, tenant_id, group_id, product_id, added_by, created_at)
-- SELECT gen_random_uuid()::text, cgm.tenant_id, cgm.group_id, cgm.content_id, 'migration', cgm.created_at
-- FROM content_group_membership cgm
-- JOIN product p ON p.id = cgm.content_id
-- WHERE cgm.content_id IN (SELECT id FROM product);
