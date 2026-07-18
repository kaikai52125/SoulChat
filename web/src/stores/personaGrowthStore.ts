import { create } from 'zustand'
import { personaGrowthApi, type GrowthData, type Milestone } from '@/api/personaGrowth'

interface PersonaGrowthState {
  growthCache: Record<string, GrowthData>
  milestoneCache: Record<string, Milestone[]>
  loading: boolean

  fetchGrowth: (personaId: string) => Promise<GrowthData>
  fetchMilestones: (personaId: string) => Promise<Milestone[]>
}

export const usePersonaGrowthStore = create<PersonaGrowthState>((set, get) => ({
  growthCache: {},
  milestoneCache: {},
  loading: false,

  fetchGrowth: async (personaId: string) => {
    const cached = get().growthCache[personaId]
    if (cached) return cached

    set({ loading: true })
    try {
      const data = await personaGrowthApi.getGrowth(personaId)
      set((s) => ({ growthCache: { ...s.growthCache, [personaId]: data } }))
      return data
    } finally {
      set({ loading: false })
    }
  },

  fetchMilestones: async (personaId: string) => {
    const cached = get().milestoneCache[personaId]
    if (cached) return cached

    const data = await personaGrowthApi.getMilestones(personaId)
    set((s) => ({ milestoneCache: { ...s.milestoneCache, [personaId]: data } }))
    return data
  },
}))
