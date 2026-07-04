import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface Persona {
  id: string
  name: string
  avatar_key: string | null
  avatar_url: string | null
  system_prompt: string
  temperature: number
  is_active: boolean

  // Agent 扩展
  memory_text: string
  tool_keys: string[]
  enable_knowledge: boolean
  enable_memory: boolean
  enable_web_search: boolean
  enable_mcp: boolean
  enable_active_recall: boolean
  enable_cross_session: boolean
  kb_ids: string[]
  conversation_scope: 'shared' | 'isolated'
  context_window: number
  human_mode: boolean
  show_avatar: boolean
}

export interface PersonaPayload {
  name: string
  avatar_key?: string | null
  system_prompt?: string
  temperature?: number
  memory_text?: string
  tool_keys?: string[]
  enable_knowledge?: boolean
  enable_memory?: boolean
  enable_web_search?: boolean
  enable_mcp?: boolean
  enable_active_recall?: boolean
  enable_cross_session?: boolean
  kb_ids?: string[]
  conversation_scope?: 'shared' | 'isolated'
  context_window?: number
  human_mode?: boolean
  show_avatar?: boolean
}

export const personaApi = {
  list(all = false) {
    return client.get<unknown, Wrapped<Persona[]>>('/personas', {
      params: all ? { all: true } : undefined,
    })
  },
  create(body: PersonaPayload) {
    return client.post<unknown, Wrapped<Persona>>('/personas', body)
  },
  update(id: string, body: Partial<PersonaPayload>) {
    return client.put<unknown, Wrapped<Persona>>(`/personas/${id}`, body)
  },
  remove(id: string) {
    return client.delete<unknown, Wrapped<null>>(`/personas/${id}`)
  },
  activate(id: string) {
    return client.post<unknown, Wrapped<Persona>>(`/personas/${id}/activate`)
  },
  stats(id: string) {
    return client.get<unknown, Wrapped<PersonaStats>>(`/personas/${id}/stats`)
  },
}

export interface PersonaStats {
  conversations: number
  messages: number
  tool_calls: number
  traces: number
  total_cost_cny: number
  skills: number
  skill_calls: number
}
