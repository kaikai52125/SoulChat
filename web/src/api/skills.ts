import client from './client'

interface Wrapped<T> {
  code: number
  message: string
  data: T
}

export interface FewShot {
  input: string
  output: string
}

export interface SkillToolDef {
  name: string
  description: string
  script: string
}

export interface SkillConfig {
  quick_prompts?: string[]
  few_shots?: FewShot[]
  is_resident?: boolean
  tools?: SkillToolDef[]
}

export interface Skill {
  id: string
  persona_id: string
  name: string
  description: string
  icon: string
  prompt: string
  tool_keys: string[]
  kb_id: string | null
  enabled: boolean
  config: SkillConfig
  source: 'builtin' | 'custom' | 'imported' | 'marketplace'
  is_builtin: boolean
  is_public: boolean
  call_count: number
}

export interface SkillInput {
  name: string
  description?: string
  icon?: string
  prompt?: string
  tool_keys?: string[]
  kb_id?: string | null
  enabled?: boolean
  is_public?: boolean
  config?: SkillConfig
}

export interface BuiltinSkill {
  key: string
  name: string
  description: string
  icon: string
  prompt: string
  tool_keys: string[]
  config: SkillConfig
}

function _url(personaId: string, suffix = '') {
  return `/personas/${personaId}/skills${suffix}`
}

export const skillApi = {
  // ── 角色内技能 ──
  list(personaId: string) {
    return client.get<unknown, Wrapped<Skill[]>>(_url(personaId))
  },
  builtins(personaId: string) {
    return client.get<unknown, Wrapped<BuiltinSkill[]>>(_url(personaId, '/builtins'))
  },
  create(personaId: string, body: SkillInput) {
    return client.post<unknown, Wrapped<Skill>>(_url(personaId), body)
  },
  addBuiltin(personaId: string, key: string) {
    return client.post<unknown, Wrapped<Skill>>(_url(personaId, `/builtins/${key}`), {})
  },
  update(personaId: string, skillId: string, body: Partial<SkillInput>) {
    return client.put<unknown, Wrapped<Skill>>(_url(personaId, `/${skillId}`), body)
  },
  remove(personaId: string, skillId: string) {
    return client.delete<unknown, Wrapped<null>>(_url(personaId, `/${skillId}`))
  },
  importZip(personaId: string, file: File) {
    const fd = new FormData()
    fd.append('file', file)
    return client.post<unknown, Wrapped<Skill>>(_url(personaId, '/import'), fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  // ── 技能市场 ──
  marketplace(limit = 50, offset = 0) {
    return client.get<unknown, Wrapped<Skill[]>>('/skills/marketplace', {
      params: { limit, offset },
    })
  },
  fork(skillId: string, personaId: string) {
    return client.post<unknown, Wrapped<Skill>>(
      `/skills/marketplace/${skillId}/fork`,
      null,
      { params: { persona_id: personaId } },
    )
  },
}
