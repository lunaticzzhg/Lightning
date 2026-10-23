import type { Strategy, StrategyDetail, Version, VersionDetail, Status } from './transport'
let token = ''
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.method === 'POST') headers.set('X-Lightning-Token', token)
  const response = await fetch(path, { ...init, headers })
  if (!response.ok) {
    let text = `请求失败（${response.status}）`
    try { const body = await response.json() as { message?: string }; text = body.message || text } catch { /* non-JSON failure */ }
    throw new Error(text)
  }
  return response.json() as Promise<T>
}
export async function connect(): Promise<void> { token = (await request<Status>('/api/status')).token }
export const api = {
  list: () => request<Strategy[]>('/api/strategies'),
  strategy: (id: string) => request<StrategyDetail>(`/api/strategies/${encodeURIComponent(id)}`),
  version: (id: string) => request<VersionDetail>(`/api/versions/${encodeURIComponent(id)}`),
  upload: (file: File, strategyId?: string) => {
    const form = new FormData(); form.append('file', file)
    return request<Version>(strategyId ? `/api/strategies/${encodeURIComponent(strategyId)}/versions` : '/api/strategies', { method: 'POST', body: form })
  },
}
