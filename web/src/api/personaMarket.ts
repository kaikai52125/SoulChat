import client from './client'
import type { Persona } from './personas'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface MarketCard {
  id: string
  persona_id: string
  market_name: string
  market_description: string
  tags: string[]
  icon: string
  downloads: number
  rating_avg: number
  rating_count: number
  version: string
  created_at: string | null
  skills?: { name: string; description: string; icon: string }[]
  mcp_servers?: { name: string }[]
}

export interface MarketDetail extends MarketCard {
  seller_user_id: string
  persona_snapshot: {
    system_prompt: string
    skills?: { name: string; description: string; icon: string; prompt: string; tool_keys: string[] }[]
    mcp_servers?: { id: string; name: string; url: string }[]
  }
  changelog: string | null
  reviews: MarketReview[]
}

export interface MarketReview {
  id: string
  user_id: string
  user_name?: string
  rating: number
  comment: string | null
  created_at: string | null
}

export interface MarketListResponse {
  items: MarketCard[]
  total: number
  page: number
  page_size: number
}

export interface PublishPayload {
  market_name: string
  market_description: string
  tags: string[]
  icon: string
}

export const personaMarketApi = {
  async listMarket(params?: {
    tag?: string[]
    sort?: 'popular' | 'newest' | 'rating'
    search?: string
    page?: number
    page_size?: number
  }): Promise<MarketListResponse> {
    const { data } = await client.get<unknown, Wrapped<MarketListResponse>>('/personas/marketplace', { params })
    return data
  },

  async getDetail(listingId: string): Promise<MarketDetail> {
    const { data } = await client.get<unknown, Wrapped<MarketDetail>>(`/personas/marketplace/${listingId}`)
    return data
  },

  async importPersona(listingId: string): Promise<Persona> {
    const { data } = await client.post<unknown, Wrapped<Persona>>(`/personas/marketplace/${listingId}/import`)
    return data
  },

  async publishPersona(personaId: string, payload: PublishPayload): Promise<{ listing_id: string }> {
    const { data } = await client.post<unknown, Wrapped<{ listing_id: string }>>(`/personas/${personaId}/publish`, payload)
    return data
  },

  async addReview(listingId: string, rating: number, _comment?: string): Promise<void> {
    await client.post(`/personas/marketplace/${listingId}/reviews`, { rating })
  },
}
