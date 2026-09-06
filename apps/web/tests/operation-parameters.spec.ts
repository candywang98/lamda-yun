import { describe, expect, it } from 'vitest'
import { buildOperationParameters, validatedPageParameters } from '@/data/operation-parameters'
import { initialPageParameters } from '@/data/operation-page-profiles'
import { operationsCatalog } from '@/data/operations-catalog'

describe('mapped operation parameter contract', () => {
  it('maps every page field of every mapped feature into parameters.pageParameters', () => {
    const mapped = operationsCatalog.filter((operation) => operation.backendOperationKey)
    expect(mapped).toHaveLength(16)

    for (const operation of mapped) {
      const values = initialPageParameters(operation.pageProfile)
      const parameters = buildOperationParameters(operation.pageProfile, values, {
        allowedParameters: ['pageParameters'],
      })
      const pageParameters = parameters.pageParameters

      expect(pageParameters, operation.id).toEqual(validatedPageParameters(operation.pageProfile, values))
      expect(Object.keys(pageParameters as object), operation.id).toEqual(operation.pageProfile.fields.map((field) => field.id))
      expect(Object.keys(pageParameters as object).length, operation.id).toBeGreaterThan(0)
    }
  })

  it('fails closed when the live server catalog does not declare pageParameters', () => {
    const operation = operationsCatalog.find((item) => item.backendOperationKey)
    expect(operation).toBeTruthy()
    expect(() => buildOperationParameters(
      operation!.pageProfile,
      initialPageParameters(operation!.pageProfile),
      { allowedParameters: [] },
    )).toThrow('Control API 未声明 pageParameters 参数合同')
  })
})
