/** 技能调用统计弹窗：汇总 + 近 30 天折线图 + 最近调用列表 */
import { useEffect, useState } from 'react'
import { Modal, Spin, Empty, Tag } from 'antd'
import {
  CheckCircleFilled,
  CloseCircleFilled,
} from '@ant-design/icons'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { skillApi, type Skill } from '@/api/skills'

interface CallStat {
  summary: {
    total: number
    success: number
    error: number
    avg_duration_ms: number
  }
  daily: Array<{ date: string; total: number; success: number; error: number }>
  recent: Array<{
    tool_name: string
    success: boolean
    duration_ms: number
    error_msg: string | null
    created_at: string | null
  }>
}

interface Props {
  open: boolean
  personaId: string
  skill: Skill | null
  onClose: () => void
}

export default function SkillDetailModal({ open, personaId, skill, onClose }: Props) {
  const [stats, setStats] = useState<CallStat | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || !skill) return
    setLoading(true)
    setStats(null)
    skillApi
      .stats(personaId, skill.id)
      .then((res) => setStats(res.data))
      .catch(() => setStats(null))
      .finally(() => setLoading(false))
  }, [open, skill, personaId])

  const s = stats?.summary
  const chartData = (stats?.daily || []).map((d) => ({
    date: d.date.slice(5), // MM-DD
    total: d.total,
    success: d.success,
    error: d.error,
  }))

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      title={skill ? `${skill.icon} ${skill.name}` : '技能统计'}
      width={620}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      ) : !stats ? (
        <Empty description="加载失败" />
      ) : s && s.total === 0 ? (
        <Empty description="暂无调用记录，触发一次技能脚本执行后即可看到数据" />
      ) : (
        <div style={{ fontSize: 13 }}>
          {/* 汇总卡片 */}
          {s && (
            <div style={{
              display: 'flex', gap: 12, marginBottom: 16,
              background: '#f6f8fa', borderRadius: 8, padding: '12px 16px',
            }}>
              <StatBadge label="总调用" value={s.total} color="#0969da" />
              <StatBadge label="成功" value={s.success} color="#1a7f37" />
              <StatBadge label="失败" value={s.error} color="#cf222e" />
              <StatBadge
                label="成功率"
                value={s.total > 0 ? `${Math.round((s.success / s.total) * 100)}%` : '-'}
                color="#8250df"
              />
              <StatBadge
                label="平均耗时"
                value={s.avg_duration_ms > 0 ? `${(s.avg_duration_ms / 1000).toFixed(1)}s` : '-'}
                color="#57606a"
              />
            </div>
          )}

          {/* 折线图 */}
          {chartData.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>📈 近 30 天调用趋势</div>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e8eaed" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 10 }} width={30} />
                  <Tooltip />
                  <Line
                    type="monotone"
                    dataKey="total"
                    stroke="#0969da"
                    strokeWidth={2}
                    dot={{ r: 2 }}
                    name="总调用"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* 最近调用 */}
          {stats.recent.length > 0 && (
            <div>
              <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 13 }}>📋 最近调用</div>
              <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                {stats.recent.slice(0, 10).map((r, i) => (
                  <div
                    key={i}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0',
                      borderBottom: '1px solid #f0f0f0', fontSize: 12,
                    }}
                  >
                    {r.success ? (
                      <CheckCircleFilled style={{ color: '#1a7f37' }} />
                    ) : (
                      <CloseCircleFilled style={{ color: '#cf222e' }} />
                    )}
                    <Tag style={{ margin: 0, fontSize: 10 }}>{r.tool_name}</Tag>
                    <span style={{ color: '#57606a' }}>
                      {r.duration_ms > 0 ? `${(r.duration_ms / 1000).toFixed(1)}s` : ''}
                    </span>
                    {r.error_msg && (
                      <span style={{ color: '#cf222e', fontSize: 10, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.error_msg.slice(0, 60)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

function StatBadge({ label, value, color }: { label: string; value: number | string; color: string }) {
  return (
    <div style={{ textAlign: 'center', flex: 1 }}>
      <div style={{ fontSize: 11, color: '#57606a' }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color }}>{value}</div>
    </div>
  )
}
