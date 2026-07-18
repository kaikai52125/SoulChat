import { useEffect, useState, useRef } from 'react'
import { Modal, Skeleton } from 'antd'
import { personaApi, type Persona, type PersonaStats } from '@/api/personas'
import { AuthenticatedImage } from '@/components/AuthenticatedImage'
import GrowthPanel from '@/components/persona/GrowthPanel'
import { personaGradientCss, personaInitial } from './personaGradient'

interface Props { open: boolean; persona: Persona | null; onClose: () => void }

const RARITY_COLORS = ['#6366f1', '#8b5cf6', '#a855f7', '#d946ef', '#f43f5e', '#f59e0b']
function rarityAccent(name: string): string {
  let h = 0; for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0
  return RARITY_COLORS[Math.abs(h) % RARITY_COLORS.length]
}

function AnimatedNumber({ value }: { value: number }) {
  const [d, setD] = useState(0); const p = useRef(0)
  useEffect(() => { const s = p.current; p.current = value; let f: number
    const step = (t: number) => { const e = Math.min((t - (s!==s?0:0)) / 600, 1); setD(Math.round(s + (value-s) * (1-Math.pow(1-e,3)))); if (e<1) f=requestAnimationFrame(step) }
    f = requestAnimationFrame(step); return () => cancelAnimationFrame(f) }, [value])
  return <span>{d.toLocaleString()}</span>
}

const STATS = [
  { k: 'traces' as const, label: '对话', icon: '💬', bg: '#eef2ff', fg: '#4f46e5' },
  { k: 'messages' as const, label: '回复', icon: '✉️', bg: '#ecfdf5', fg: '#059669' },
  { k: 'tool_calls' as const, label: '工具', icon: '⚡', bg: '#fffbeb', fg: '#d97706' },
  { k: 'mcp_calls' as const, label: 'MCP', icon: '🔗', bg: '#ecfeff', fg: '#0891b2' },
  { k: 'skills' as const, label: '技能', icon: '🎯', bg: '#fdf2f8', fg: '#db2777' },
  { k: 'skill_calls' as const, label: '调用', icon: '🔥', bg: '#faf5ff', fg: '#9333ea' },
]

const TOGGLES: [keyof Persona, string, string][] = [
  ['enable_knowledge', '知识库', '📚'], ['enable_memory', '记忆', '🧠'],
  ['enable_web_search', '联网', '🌐'], ['enable_mcp', 'MCP', '🔌'],
  ['enable_active_recall', '主动召回', '💡'], ['enable_cross_session', '跨会话', '🔄'],
]

export default function PersonaDetailModal({ open, persona, onClose }: Props) {
  const [stats, setStats] = useState<PersonaStats | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open && persona) {
      setLoading(true)
      personaApi.stats(persona.id).then(({ data }) => setStats(data)).catch(() => setStats(null)).finally(() => setLoading(false))
    }
    if (!open) setStats(null)
  }, [open, persona])

  if (!persona) return null
  const accent = rarityAccent(persona.name)

  return (
    <Modal open={open} onCancel={onClose} footer={null} title={null} width={600}
      styles={{ body: { padding: 0 }, content: { padding: 0, background: '#f8fafc', borderRadius: 16, overflow: 'hidden' } }}
    >
      <div style={{ background: '#f8fafc', overflow: 'hidden' }}>
        {/* HERO */}
        <div style={{
          position: 'relative', padding: '32px 28px 24px',
          background: `linear-gradient(180deg, ${accent}14 0%, ${accent}06 50%, #f8fafc 100%)`,
        }}>
          <div style={{ position: 'absolute', top: -60, left: '50%', transform: 'translateX(-50%)', width: 200, height: 200, borderRadius: '50%', background: `radial-gradient(circle, ${accent}20 0%, transparent 70%)` }} />

          <div style={{ position: 'absolute', top: 48, right: 28, zIndex: 1 }}>
            <div style={{
              background: `linear-gradient(135deg, ${accent}, ${accent}dd)`,
              borderRadius: 14, padding: '6px 18px', color: '#fff',
              textAlign: 'center',
              boxShadow: `0 4px 16px ${accent}30`,
            }}>
              <div style={{ fontSize: 10, opacity: 0.75, letterSpacing: 1 }}>LEVEL</div>
              <div style={{ fontSize: 28, fontWeight: 900, lineHeight: '32px' }}>{persona.growth?.level ?? 1}</div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, position: 'relative', zIndex: 1 }}>
            <div style={{
              width: 84, height: 84, borderRadius: 26, padding: 3,
              background: `linear-gradient(135deg, ${accent}, ${accent}66)`,
              boxShadow: `0 8px 32px ${accent}28`,
            }}>
              {persona.avatar_url ? (
                <AuthenticatedImage src={persona.avatar_url} alt={persona.name}
                  style={{ width: '100%', height: '100%', borderRadius: 23, objectFit: 'cover', display: 'block' }} />
              ) : (
                <div style={{
                  width: '100%', height: '100%', borderRadius: 23, display: 'flex',
                  alignItems: 'center', justifyContent: 'center',
                  fontSize: 34, fontWeight: 800, color: '#fff',
                  background: personaGradientCss(persona.name),
                }}>{personaInitial(persona.name)}</div>
              )}
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: '#0f172a', letterSpacing: -0.3 }}>{persona.name}</div>
              <div style={{ marginTop: 4, display: 'flex', gap: 6, justifyContent: 'center' }}>
                {persona.is_active && <span style={{ fontSize: 11, padding: '2px 10px', borderRadius: 6, background: accent, color: '#fff', fontWeight: 600 }}>✦ 当前</span>}
                {persona.human_mode && <span style={{ fontSize: 11, padding: '2px 10px', borderRadius: 6, background: '#fef3c7', color: '#92400e', fontWeight: 600 }}>真人</span>}
                {persona.cloned_from_id && <span style={{ fontSize: 11, padding: '2px 10px', borderRadius: 6, background: '#e2e8f0', color: '#475569' }}>导入</span>}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 20, maxWidth: 300, margin: '14px auto 0', position: 'relative', zIndex: 1 }}>
            <div style={{ flex: 1, textAlign: 'center' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 10, color: '#94a3b8' }}>温度</span>
                <span style={{ fontSize: 11, fontWeight: 600, color: '#334155' }}>{persona.temperature.toFixed(1)}</span>
              </div>
              <div style={{ height: 4, borderRadius: 2, background: '#e2e8f0', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${(persona.temperature / 2) * 100}%`, borderRadius: 2, background: `linear-gradient(90deg, ${accent}, #f59e0b)`, transition: 'width 0.5s' }} />
              </div>
            </div>
            {persona.growth && (
              <div style={{ flex: 1, textAlign: 'center' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 10, color: '#94a3b8' }}>亲密</span>
                  <span style={{ fontSize: 11, fontWeight: 600, color: '#334155' }}>{persona.growth.intimacy}</span>
                </div>
                <div style={{ height: 4, borderRadius: 2, background: '#e2e8f0', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${persona.growth.intimacy}%`, borderRadius: 2, background: 'linear-gradient(90deg, #f472b6, #fb923c)', transition: 'width 0.5s' }} />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* STATS */}
        <div style={{ padding: '0 24px' }}>
          {loading ? <Skeleton active paragraph={{ rows: 1 }} /> : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 6 }}>
              {STATS.map((s) => (
                <div key={s.k} style={{
                  textAlign: 'center', padding: '10px 4px', borderRadius: 12,
                  background: s.bg, border: '1px solid rgba(0,0,0,0.03)',
                }}>
                  <div style={{ fontSize: 16 }}>{s.icon}</div>
                  <div style={{ fontSize: 17, fontWeight: 700, color: s.fg, marginTop: 1 }}>
                    {stats ? <AnimatedNumber value={Number(stats[s.k]) || 0} /> : '-'}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div style={{
            marginTop: 8, padding: '10px 14px', borderRadius: 12,
            background: '#fff', border: '1px solid #f1f5f9',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}>
            <span style={{ fontSize: 12, color: '#64748b' }}>累计花费</span>
            <span style={{ fontSize: 14, fontWeight: 700, color: '#d97706' }}>{stats ? `¥${stats.total_cost_cny.toFixed(4)}` : '-'}</span>
          </div>
        </div>

        {/* GROWTH */}
        <div style={{ padding: '20px 24px' }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', letterSpacing: 1.5, textTransform: 'uppercase', marginBottom: 10 }}>Growth</div>
          <div style={{ borderRadius: 16, background: '#fff', border: '1px solid #f1f5f9', padding: '16px 18px', boxShadow: '0 1px 3px rgba(0,0,0,0.03)' }}>
            <GrowthPanel personaId={persona.id} />
          </div>
        </div>

        {/* MODULES & PERSONA */}
        <div style={{ padding: '0 24px 24px' }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', letterSpacing: 1.5, textTransform: 'uppercase', marginBottom: 10 }}>Modules</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
            {TOGGLES.map(([key, label, icon]) => {
              const on = persona[key] as boolean
              return (
                <div key={key} style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '8px 12px', borderRadius: 10,
                  background: on ? '#f0fdf4' : '#fff',
                  border: `1px solid ${on ? '#bbf7d0' : '#f1f5f9'}`,
                }}>
                  <span style={{ fontSize: 14 }}>{icon}</span>
                  <span style={{ fontSize: 12, fontWeight: 500, color: on ? '#166534' : '#94a3b8', flex: 1 }}>{label}</span>
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: on ? '#22c55e' : '#cbd5e1', boxShadow: on ? '0 0 5px #22c55e60' : 'none' }} />
                </div>
              )
            })}
          </div>

          {persona.system_prompt && (
            <>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', letterSpacing: 1.5, textTransform: 'uppercase', marginTop: 16, marginBottom: 10 }}>Persona</div>
              <div style={{
                padding: '12px 14px', borderRadius: 10,
                background: '#fff', border: '1px solid #f1f5f9',
                fontSize: 12, lineHeight: 1.7, color: '#475569', maxHeight: 72, overflow: 'auto',
                whiteSpace: 'pre-wrap',
              }}>{persona.system_prompt}</div>
            </>
          )}
        </div>
      </div>
    </Modal>
  )
}
