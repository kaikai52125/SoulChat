import { useEffect, useState } from 'react'
import { Descriptions, Modal, Spin, Statistic, Tag } from 'antd'
import {
  CommentOutlined,
  DollarOutlined,
  MessageOutlined,
  ThunderboltOutlined,
  ToolOutlined,
} from '@ant-design/icons'
import { personaApi, type Persona, type PersonaStats } from '@/api/personas'

interface Props {
  open: boolean
  persona: Persona | null
  onClose: () => void
}

export default function PersonaDetailModal({ open, persona, onClose }: Props) {
  const [stats, setStats] = useState<PersonaStats | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open && persona) {
      setLoading(true)
      personaApi.stats(persona.id)
        .then(({ data }) => setStats(data))
        .catch(() => setStats(null))
        .finally(() => setLoading(false))
    }
    if (!open) setStats(null)
  }, [open, persona])

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      title={persona ? `${persona.name} · 详情` : '角色详情'}
      width={560}
    >
      {loading ? (
        <Spin style={{ display: 'block', padding: 40 }} />
      ) : stats ? (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 20 }}>
            <Statistic title="对话轮次" value={stats.traces} prefix={<CommentOutlined />} />
            <Statistic title="回复数" value={stats.messages} prefix={<MessageOutlined />} />
            <Statistic title="工具调用" value={stats.tool_calls} prefix={<ToolOutlined />} />
            <Statistic title="技能数" value={stats.skills} />
            <Statistic title="技能调用" value={stats.skill_calls} prefix={<ThunderboltOutlined />} />
            <Statistic
              title="总成本"
              value={stats.total_cost_cny.toFixed(4)}
              prefix={<DollarOutlined />}
              suffix="¥"
            />
          </div>

          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="人设提示词">
              <div style={{ maxHeight: 100, overflow: 'auto', whiteSpace: 'pre-wrap', fontSize: 12 }}>
                {persona?.system_prompt || '(空)'}
              </div>
            </Descriptions.Item>
            <Descriptions.Item label="角色记忆">
              {persona?.memory_text ? `${persona.memory_text.length} 字符` : '无'}
            </Descriptions.Item>
          </Descriptions>

          <div style={{ marginTop: 16, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <Tag color={persona?.enable_knowledge ? 'blue' : 'default'}>
              知识库{persona?.enable_knowledge ? '✓' : '✗'}
            </Tag>
            <Tag color={persona?.enable_memory ? 'blue' : 'default'}>
              记忆{persona?.enable_memory ? '✓' : '✗'}
            </Tag>
            <Tag color={persona?.enable_web_search ? 'blue' : 'default'}>
              联网{persona?.enable_web_search ? '✓' : '✗'}
            </Tag>
            <Tag color={persona?.conversation_scope === 'isolated' ? 'purple' : 'default'}>
              {persona?.conversation_scope === 'isolated' ? '隔离对话' : '共享对话'}
            </Tag>
            {persona?.human_mode && <Tag color="orange">真人模式</Tag>}
          </div>
        </div>
      ) : (
        <div style={{ textAlign: 'center', color: '#98a2b3', padding: 40 }}>暂无统计数据</div>
      )}
    </Modal>
  )
}
