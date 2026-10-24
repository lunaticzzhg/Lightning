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

export const marketApi = {
  sources: async () => unwrap(await client.GET('/api/market/sources')),
  search: async (symbol: string, period: string, fromDate: string, toDate: string, market?: string) => unwrap(await client.GET('/api/market/search', { params: { query: { symbol, period, from_date: fromDate, to_date: toDate, market } } })),
  stage: async (file: File, targetDatasetId?: string) => unwrap(await client.POST('/api/market/drafts', { params: { header: { 'X-Lightning-Token': token }, query: { target_dataset_id: targetDatasetId } }, body: { file }, bodySerializer: multipart })),
  preview: async (draftId: string, volumeUnit: string, minutePosition?: string, exchange?: string) => unwrap(await client.POST('/api/market/drafts/{draft_id}/preview', { params: { path: { draft_id: draftId }, header: { 'X-Lightning-Token': token } }, body: { volume_unit: volumeUnit, minute_position: minutePosition, exchange } })),
  compare: async (draftId: string, body: import('./openapi').components['schemas']['MarketImportChoice'], page = 1) => unwrap(await client.POST('/api/market/drafts/{draft_id}/compare', { params: { path: { draft_id: draftId }, query: { page }, header: { 'X-Lightning-Token': token } }, body })),
  publish: async (draftId: string, body: import('./openapi').components['schemas']['MarketConfirmChoice']) => unwrap(await client.POST('/api/market/drafts/{draft_id}/publish', { params: { path: { draft_id: draftId }, header: { 'X-Lightning-Token': token } }, body })),
  result: async (draftId: string) => unwrap(await client.GET('/api/market/drafts/{draft_id}/result', { params: { path: { draft_id: draftId } } })),
  importRecord: async (versionId: string) => unwrap(await client.GET('/api/market/versions/{version_id}/import-record', { params: { path: { version_id: versionId } } })),
  versions: async (datasetId: string) => unwrap(await client.GET('/api/market/datasets/{dataset_id}/versions', { params: { path: { dataset_id: datasetId } } })),
  chart: async (datasetId: string, versionId: string, symbol: string, fromDate: string, toDate: string, exchange?: string, start?: string, end?: string) => unwrap(await client.GET('/api/market/datasets/{dataset_id}/versions/{version_id}/chart', { params: { path: { dataset_id: datasetId, version_id: versionId }, query: { symbol, from_date: fromDate, to_date: toDate, exchange, start, end } } })),
}
