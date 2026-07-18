import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface DiaryEntry {
  id: string
  persona_id: string
  diary_date: string | null
  title: string | null
  content: string
  mood: string | null
  key_topics: string[]
  word_count: number
  is_read: boolean
  created_at: string | null
}

export interface DiaryListResponse {
  items: DiaryEntry[]
  total: number
  page: number
  page_size: number
}

export const personaDiaryApi = {
  async listDiaries(params?: {
    persona_id?: string
    page?: number
    page_size?: number
  }): Promise<DiaryListResponse> {
    const { data } = await client.get<unknown, Wrapped<DiaryListResponse>>('/diaries', { params })
    return data
  },

  async getUnreadCount(): Promise<number> {
    const { data } = await client.get<unknown, Wrapped<{ count: number }>>('/diaries/unread-count')
    return data.count
  },

  async markRead(diaryId: string): Promise<void> {
    await client.put(`/diaries/${diaryId}/read`)
  },
}
