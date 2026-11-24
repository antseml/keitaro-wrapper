export interface Option { id: number; name: string }
export interface Meta { domains: Option[]; groups: Option[]; sources: Option[] }
export interface Campaign { id: number; name: string; alias: string; url: string | null }
export interface Offer extends Option { share: number; pinned: boolean; removed: boolean }
export interface Stream {
  id: number
  name: string
  type: string
  editable: boolean
  dirty: boolean
  state: 'active' | 'disabled' | string
  offers: Offer[]
}
export interface StreamList { campaign_id: number; streams: Stream[] }
export interface CreateCampaign {
  name: string
  geo: string
  offer_id: number
  domain_id: number
  group_id: number
  source_id: number
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new Error('Нет соединения с сервером. Проверьте, что FastAPI запущен')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string | { msg?: string }[] }
    const message = Array.isArray(body.detail)
      ? body.detail.map(item => item.msg ?? 'Ошибка проверки').join('; ')
      : body.detail
    throw new Error(message || `Ошибка запроса (${response.status})`)
  }
  return response.json() as Promise<T>
}

const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

export const api = {
  meta: () => request<Meta>('/meta'),
  offers: (query: string) => request<Option[]>(`/offers?q=${encodeURIComponent(query)}`),
  campaigns: (query: string) => request<Campaign[]>(`/campaigns?q=${encodeURIComponent(query)}`),
  create: (payload: CreateCampaign) => request<Campaign>('/campaigns', json(payload)),
  streams: (campaignId: number) => request<StreamList>(`/campaigns/${campaignId}/streams`),
  sync: (campaignId: number) => request<StreamList>(`/campaigns/${campaignId}/sync`, { method: 'POST' }),
  add: (streamId: number, offerId: number) => request<Stream>(`/streams/${streamId}/offers`, json({ offer_id: offerId })),
  remove: (streamId: number, offerId: number) => request<Stream>(`/streams/${streamId}/offers/${offerId}`, { method: 'DELETE' }),
  purge: (streamId: number, offerId: number) => request<Stream>(`/streams/${streamId}/offers/${offerId}/archive`, { method: 'DELETE' }),
  restore: (streamId: number, offerId: number) => request<Stream>(`/streams/${streamId}/offers/${offerId}/restore`, { method: 'POST' }),
  pin: (streamId: number, offerId: number, pinned: boolean, share: number) =>
    request<Stream>(`/streams/${streamId}/offers/${offerId}/pin`, {
      method: 'PUT', body: JSON.stringify({ pinned, share }),
    }),
  publish: (streamId: number) => request<Stream>(`/streams/${streamId}/publish`, { method: 'POST' }),
  cancel: (streamId: number) => request<Stream>(`/streams/${streamId}/cancel`, { method: 'POST' }),
}
