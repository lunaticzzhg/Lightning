import createClient from 'openapi-fetch'
import type { paths } from './openapi'

const client = createClient<paths>()
let token = ''

async function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): Promise<T> {
  if (result.response.ok && result.data !== undefined) return result.data
  let error = result.error
  if (error instanceof Blob) {
    try { error = JSON.parse(await error.text()) } catch { /* non-JSON response */ }
  }
  const message = typeof error === 'object' && error !== null && 'message' in error && typeof error.message === 'string'
    ? error.message : `请求失败（${result.response.status}）`
  throw new Error(message)
}

const multipart = (body: { file: Blob }) => {
  const form = new FormData()
  form.append('file', body.file)
  return form
}

export async function connect(): Promise<void> {
  const result = await client.GET('/api/status')
  token = (await unwrap(result)).token
}

export const api = {
  list: async () => unwrap(await client.GET('/api/strategies')),
  strategy: async (id: string) => unwrap(await client.GET('/api/strategies/{strategy_id}', { params: { path: { strategy_id: id } } })),
  version: async (id: string) => unwrap(await client.GET('/api/versions/{version_id}', { params: { path: { version_id: id } } })),
  upload: async (file: File, strategyId?: string) => {
    const options = { params: { header: { 'X-Lightning-Token': token } }, body: { file }, bodySerializer: multipart }
    return strategyId
      ? unwrap(await client.POST('/api/strategies/{strategy_id}/versions', { ...options, params: { ...options.params, path: { strategy_id: strategyId } } }))
      : unwrap(await client.POST('/api/strategies', options))
  },
  download: async (id: string) => {
    const result = await client.GET('/api/versions/{version_id}/download', { params: { path: { version_id: id } }, parseAs: 'blob' })
    const blob = await unwrap(result)
    const disposition = result.response.headers.get('content-disposition') ?? ''
    const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1]
    let fileName = 'strategy.zip'
    if (encoded) {
      try { fileName = decodeURIComponent(encoded) } catch { /* malformed filename */ }
    }
    return { blob, fileName }
  },
}
