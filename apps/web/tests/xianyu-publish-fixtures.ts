import type { ProductView } from '@cloudctl/api-contracts'
import type { XianyuPublishQueueRequest } from '@/data/xianyu-publish-goods'

export function product(overrides: Partial<ProductView> = {}): ProductView {
  return {
    id: 'product-1', spuCode: 'SKU-1', title: 'Test product', description: 'Catalog description',
    price: '12.50', category: 'test', stock: 1, status: 'ACTIVE', revision: 1,
    mediaAssetIds: ['asset-1', 'asset-2'],
    media: [{ mediaAssetId: 'asset-1', sortOrder: 0, role: 'cover' }, { mediaAssetId: 'asset-2', sortOrder: 1, role: 'detail' }],
    createdAt: '2026-09-29T00:00:00Z', ...overrides,
  }
}

export function queueResponse(request: XianyuPublishQueueRequest) {
  return {
    queueId: request.queueId, deviceId: request.deviceId, accountId: request.accountId,
    replayed: false, serialAdvanceBlocked: false,
    targets: request.items.map((item, position) => ({
      targetId: `target-${position}`, queueId: request.queueId, deviceId: request.deviceId,
      accountId: request.accountId, position, item: { ...item }, claimedBoundary: item.completionBoundary,
      state: 'PENDING', taskIds: [] as string[], externalItemId: null as string | null,
      recordedBoundary: null, boundaryDowngraded: false, judgment: {}, result: {}, confirmedAt: null,
    })),
  }
}

export function account(deviceId = 'device-1', id = 'account-1') {
  return {
    id, tenantId: 'tenant-1', platform: 'xianyu', externalSubjectRef: 'seller-1',
    displayLabel: 'Seller', secretConfigured: true, authorizationBasis: 'test fixture',
    status: 'AUTHORIZED', expiresAt: null, lastCheckedAt: null, revokedAt: null, version: 1,
    createdAt: '2026-09-29T00:00:00Z',
    bindings: [{
      id: `binding-${id}`, accountId: id, deviceId, status: 'BOUND', platform: 'xianyu',
      confirmedBy: 'operator-1', confirmationNote: 'test fixture',
      boundAt: '2026-09-29T00:00:00Z', unboundAt: null, bindingVersion: 1, historical: false,
    }],
  }
}

export function device(id = 'device-1') {
  return { id, logical_name: id, last_seen_at: new Date().toISOString(), capabilities: {} }
}
