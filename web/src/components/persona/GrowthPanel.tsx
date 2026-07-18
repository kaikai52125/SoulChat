import { useEffect, useState } from 'react'
import { Timeline, Typography, Row, Col, Skeleton } from 'antd'
import {
  ThunderboltOutlined,
  ClockCircleOutlined,
  ToolOutlined,
  StarFilled,
} from '@ant-design/icons'
import { usePersonaGrowthStore } from '@/stores/personaGrowthStore'
import type { GrowthData, Milestone } from '@/api/personaGrowth'

const { Text } = Typography

const TRAIT_DEFS: Record<string, { name: string; icon: string; color: string; desc: string }> = {
  memory_savant: { name: '记忆达人', icon: '🧠', color: '#a78bfa', desc: '更自然地引用旧记忆，让对话有温度' },
  humor_unlock: { name: '幽默模块', icon: '😄', color: '#f59e0b', desc: '在合适时机展现幽默感' },
  emotion_aware: { name: '情绪感知', icon: '💙', color: '#3b82f6', desc: '敏锐察觉你的情绪变化' },
  style_mirror: { name: '风格镜映', icon: '🪞', color: '#8b5cf6', desc: '微妙调整语气来匹配你' },
  proactive_care: { name: '主动关心', icon: '🤗', color: '#ec4899', desc: '主动关心你之前提过的事' },
  deep_insight: { name: '深度洞察', icon: '🔍', color: '#6366f1', desc: '帮你看清问题背后的本质' },
  memory_guardian: { name: '记忆守护', icon: '🛡️', color: '#f43f5e', desc: '帮你记住生命中重要的事' },
}

function MiniStat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div style={{
      textAlign: 'center',
      padding: '8px 4px',
      borderRadius: 10,
      background: 'rgba(255,255,255,0.65)',
      backdropFilter: 'blur(6px)',
      border: '1px solid rgba(0,0,0,0.04)',
    }}>
      <div style={{ fontSize: 18, marginBottom: 2 }}>{icon}</div>
      <div style={{ fontSize: 18, fontWeight: 800, color: '#1e293b', lineHeight: '22px' }}>{value}</div>
      <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 1 }}>{label}</div>
    </div>
  )
}

export default function GrowthPanel({ personaId }: Props) {
  const { fetchGrowth, fetchMilestones } = usePersonaGrowthStore()
  const [growth, setGrowth] = useState<GrowthData | null>(null)
  const [milestones, setMilestones] = useState<Milestone[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([fetchGrowth(personaId), fetchMilestones(personaId)])
      .then(([g, m]) => {
        if (!cancelled) {
          setGrowth(g)
          setMilestones(m)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setGrowth({ xp: 0, level: 1, intimacy: 0, interaction_count: 0, consecutive_days: 0, total_tool_calls: 0, unlocked_traits: [], xp_to_next: 100, xp_total_next: 100, xp_progress_pct: 0 })
          setMilestones([])
        }
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [personaId])

  if (loading) {
    return (
      <div style={{ padding: '12px 0' }}>
        <Row gutter={[10, 10]}>
          {[1, 2, 3, 4].map((i) => <Col span={12} key={i}><Skeleton active paragraph={{ rows: 1 }} /></Col>)}
        </Row>
        <Skeleton active paragraph={{ rows: 2 }} style={{ marginTop: 14 }} />
      </div>
    )
  }

  const renderGrowth = growth!

  return (
    <div style={{ padding: '12px 0' }}>
      {/* ── XP 进度条 ── */}
      <div style={{
        borderRadius: 14,
        padding: '14px 18px',
        background: 'rgba(255,255,255,0.6)',
        backdropFilter: 'blur(8px)',
        border: '1px solid rgba(0,0,0,0.04)',
        marginBottom: 14,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: '#334155' }}>
            <ThunderboltOutlined style={{ color: '#6366f1', marginRight: 4 }} />经验值
          </span>
          <span style={{ fontSize: 12, color: '#6366f1', fontWeight: 700 }}>
            {renderGrowth.xp.toLocaleString()} <span style={{ color: '#94a3b8', fontWeight: 400 }}>/ {renderGrowth.xp_progress_pct > 0 ? (renderGrowth.xp + renderGrowth.xp_to_next).toLocaleString() : '—'} XP</span>
          </span>
        </div>
        <div style={{
          height: 10,
          borderRadius: 5,
          background: '#e2e8f0',
          overflow: 'hidden',
        }}>
          <div style={{
            height: '100%',
            width: `${renderGrowth.xp_progress_pct}%`,
            borderRadius: 5,
            background: 'linear-gradient(90deg, #818cf8, #6366f1, #4f46e5)',
            transition: 'width 0.8s cubic-bezier(0.4, 0, 0.2, 1)',
          }} />
        </div>
        <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 4, textAlign: 'right' }}>
          距离 Lv.{renderGrowth.level + 1} 还需 {renderGrowth.xp_to_next.toLocaleString()} XP
        </div>
      </div>

      {/* ── 迷你统计 ── */}
      <Row gutter={[8, 8]} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <MiniStat icon={<ClockCircleOutlined style={{ color: '#f59e0b' }} />} label="连续" value={`${renderGrowth.consecutive_days}天`} />
        </Col>
        <Col span={6}>
          <MiniStat icon={<ToolOutlined style={{ color: '#10b981' }} />} label="工具" value={renderGrowth.total_tool_calls} />
        </Col>
        <Col span={6}>
          <MiniStat icon="💬" label="互动" value={renderGrowth.interaction_count} />
        </Col>
        <Col span={6}>
          <MiniStat icon="🔓" label="特质" value={renderGrowth.unlocked_traits.length} />
        </Col>
      </Row>

      {/* ── 特质 ── */}
      <div style={{
        borderRadius: 14,
        padding: '14px 16px',
        background: 'rgba(255,255,255,0.4)',
        backdropFilter: 'blur(8px)',
        border: '1px solid rgba(0,0,0,0.03)',
        marginBottom: 16,
      }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: '#334155', marginBottom: 10 }}>
          🏆 已解锁特质
        </div>
        {renderGrowth.unlocked_traits.length === 0 ? (
          <Text type="secondary" style={{ fontSize: 12 }}>继续聊天来解锁特质…</Text>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {renderGrowth.unlocked_traits.map((key) => {
              const t = TRAIT_DEFS[key]
              if (!t) return null
              return (
                <div key={key} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '8px 12px', borderRadius: 10,
                  background: `${t.color}10`, border: `1px solid ${t.color}30`,
                }}>
                  <span style={{ fontSize: 20 }}>{t.icon}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#1e293b' }}>{t.name}</div>
                    <div style={{ fontSize: 11, color: '#64748b' }}>{t.desc}</div>
                  </div>
                  <div style={{
                    width: 6, height: 6, borderRadius: '50%',
                    background: t.color, boxShadow: `0 0 6px ${t.color}`,
                  }} />
                </div>
              )
            })}
          </div>
        )}
        {/* 未解锁预览 */}
        <div style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 10 }}>后续解锁：</Text>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
            {Object.entries(TRAIT_DEFS)
              .filter(([key]) => !renderGrowth.unlocked_traits.includes(key))
              .slice(0, 4)
              .map(([key, t]) => (
                <span key={key} style={{
                  fontSize: 11, padding: '2px 8px', borderRadius: 6,
                  background: 'rgba(0,0,0,0.04)', color: '#94a3b8',
                }}>
                  🔒 {t.name}
                </span>
              ))}
          </div>
        </div>
      </div>

      {/* ── 里程碑 ── */}
      {milestones.length > 0 && (
        <div style={{
          borderRadius: 14,
          padding: '14px 16px',
          background: 'rgba(255,255,255,0.4)',
          backdropFilter: 'blur(8px)',
          border: '1px solid rgba(0,0,0,0.03)',
        }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#334155', marginBottom: 8 }}>
            <StarFilled style={{ color: '#f59e0b', marginRight: 4 }} />成长里程碑
          </div>
          <Timeline
            items={milestones.slice(0, 12).map((m) => ({
              dot: <span style={{ fontSize: 12 }}>⭐</span>,
              children: (
                <div>
                  <span style={{ fontSize: 12, fontWeight: 600, color: '#334155' }}>{m.title}</span>
                  <br />
                  <span style={{ fontSize: 11, color: '#94a3b8' }}>{m.description}</span>
                </div>
              ),
            }))}
          />
        </div>
      )}
    </div>
  )
}

interface Props { personaId: string }
