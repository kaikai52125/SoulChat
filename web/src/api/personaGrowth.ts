import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface GrowthData {
  xp: number
  level: number
  intimacy: number
  interaction_count: number
  consecutive_days: number
  total_tool_calls: number
  unlocked_traits: string[]
  xp_to_next: number
  xp_total_next: number
  xp_progress_pct: number
}

export interface Milestone {
  id: string
  type: string
  type_name: string
  title: string
  description: string
  level_at_trigger: number | null
  occurred_at: string | null
}

export const personaGrowthApi = {
  async getGrowth(personaId: string): Promise<GrowthData> {
    const { data } = await client.get<unknown, Wrapped<GrowthData>>(`/personas/${personaId}/growth`)
    return data
  },

  async getMilestones(personaId: string): Promise<Milestone[]> {
    const { data } = await client.get<unknown, Wrapped<Milestone[]>>(`/personas/${personaId}/milestones`)
    return data
  },
}
