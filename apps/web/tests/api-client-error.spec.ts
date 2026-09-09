import { describe, expect, it, vi } from 'vitest'
import { CloudCtlApiClient } from '@cloudctl/api-contracts'

describe('CloudCtlApiClient error responses', () => {
  it('preserves a non-JSON server error instead of throwing a JSON syntax error', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('Internal Server Error', {
      status: 500,
      statusText: 'Internal Server Error',
      headers: {
        'Content-Type': 'text/plain',
        'X-Request-Id': 'request-500',
      },
    }))
    const client = new CloudCtlApiClient({
      baseUrl: 'https://control.example.test',
      fetch: fetcher as typeof fetch,
    })

    const request = client.createContent({
      title: '测试帖子',
      payload: { kind: 'post', body: '测试内容' },
    })

    await expect(request).rejects.toMatchObject({
      name: 'CloudCtlApiError',
      status: 500,
      problem: {
        type: 'about:blank',
        title: 'Internal Server Error',
        status: 500,
        code: 'HTTP_500',
        detail: 'Request failed with HTTP 500: Internal Server Error',
        correlation_id: 'request-500',
        retryable: true,
        fields: {},
      },
    })
  })

  it('keeps structured problem details returned as JSON', async () => {
    const problem = {
      type: 'urn:cloudctl:problem:validation',
      title: 'Validation failed',
      status: 422,
      code: 'VALIDATION_FAILED',
      detail: '请求字段无效',
      correlation_id: 'request-422',
      retryable: false,
      fields: { title: '不能为空' },
    }
    const client = new CloudCtlApiClient({
      baseUrl: 'https://control.example.test',
      fetch: vi.fn().mockResolvedValue(Response.json(problem, { status: 422 })) as typeof fetch,
    })

    await expect(client.createContent({ title: '测试', payload: {} })).rejects.toMatchObject({
      name: 'CloudCtlApiError',
      status: 422,
      problem,
    })
  })
})
