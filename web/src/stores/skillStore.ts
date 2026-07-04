import { create } from 'zustand'
import { skillApi, type Skill } from '@/api/skills'

interface SkillState {
  list: Skill[]
  personaId: string | null
  loading: boolean
  /** 为指定 persona 加载技能列表，若 persona 不变且已加载则跳过 */
  loadForPersona: (personaId: string) => Promise<void>
  refresh: (personaId: string) => Promise<void>
  clear: () => void
}

export const useSkillStore = create<SkillState>((set, get) => ({
  list: [],
  personaId: null,
  loading: false,
  loadForPersona: async (personaId: string) => {
    if (get().personaId === personaId && get().list.length > 0) return
    await get().refresh(personaId)
  },
  refresh: async (personaId: string) => {
    set({ loading: true })
    try {
      const { data } = await skillApi.list(personaId)
      set({ list: data, personaId })
    } catch {
      // 角色不存在或已删除时静默失败，不弹错误
      set({ list: [], personaId })
    } finally {
      set({ loading: false })
    }
  },
  clear: () => set({ list: [], personaId: null }),
}))
