import { useEffect, useState } from 'react'
import { Card, Col, Descriptions, Modal, Row, Statistic, Tag, Typography } from 'antd'
import {
  ApiOutlined,
  CommentOutlined,
  MessageOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  ToolOutlined,
} from '@ant-design/icons'
import { personaApi, type Persona, type PersonaStats } from '@/api/personas'
import { AuthenticatedImage } from '@/components/AuthenticatedImage'

const { Text } = Typography

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
      title={null}
      width={620}
      styles={{ body: { padding: 0 } }}
    >
      {!persona ? null : (
        <div>
          {/* 头部：名称 + 状态 */}
          <div
            style={{
              padding: '24px 24px 0',
              display: 'flex', alignItems: 'center', gap: 16,
            }}
          >
            {persona.avatar_url ? (
              <AuthenticatedImage
                src={persona.avatar_url}
                alt={persona.name}
                style={{
                  width: 56, height: 56, borderRadius: 16, objectFit: 'cover', flexShrink: 0,
                }}
              />
            ) : (
              <div
                style={{
                  width: 56, height: 56, borderRadius: 16,
                  background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: '#fff', fontSize: 26, fontWeight: 700, flexShrink: 0,
                }}
              >
                {persona.name.slice(0, 2)}
              </div>
            )}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 20, fontWeight: 700, color: '#1d2129' }}>
                {persona.name}
              </div>
              <div style={{ marginTop: 4, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {persona.is_active && <Tag color="blue">当前使用</Tag>}
                {persona.human_mode && <Tag color="orange">真人模式</Tag>}
                {persona.conversation_scope === 'isolated' && <Tag color="purple">隔离对话</Tag>}
              </div>
            </div>
          </div>

          {/* 统计卡片 */}
          <div style={{ padding: '24px 24px 0' }}>
            <Row gutter={[12, 12]}>
              <Col span={6}>
                <Card size="small" style={{ background: '#f0f5ff', border: 'none', borderRadius: 12 }}>
                  <Statistic
                    title={<Text style={{ fontSize: 12, color: '#667085' }}>对话轮次</Text>}
                    value={stats?.traces ?? '-'}
                    prefix={<CommentOutlined style={{ fontSize: 16, color: '#155EEF' }} />}
                    valueStyle={{ fontSize: 22, fontWeight: 700, color: '#155EEF' }}
                    loading={loading}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ background: '#f6ffed', border: 'none', borderRadius: 12 }}>
                  <Statistic
                    title={<Text style={{ fontSize: 12, color: '#667085' }}>回复数</Text>}
                    value={stats?.messages ?? '-'}
                    prefix={<MessageOutlined style={{ fontSize: 16, color: '#52c41a' }} />}
                    valueStyle={{ fontSize: 22, fontWeight: 700, color: '#52c41a' }}
                    loading={loading}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ background: '#fff7e6', border: 'none', borderRadius: 12 }}>
                  <Statistic
                    title={<Text style={{ fontSize: 12, color: '#667085' }}>工具调用</Text>}
                    value={stats?.tool_calls ?? '-'}
                    prefix={<ToolOutlined style={{ fontSize: 16, color: '#fa8c16' }} />}
                    valueStyle={{ fontSize: 22, fontWeight: 700, color: '#fa8c16' }}
                    loading={loading}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ background: '#e6fffb', border: 'none', borderRadius: 12 }}>
                  <Statistic
                    title={<Text style={{ fontSize: 12, color: '#667085' }}>MCP 调用</Text>}
                    value={stats?.mcp_calls ?? '-'}
                    prefix={<ApiOutlined style={{ fontSize: 16, color: '#13c2c2' }} />}
                    valueStyle={{ fontSize: 22, fontWeight: 700, color: '#13c2c2' }}
                    loading={loading}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ background: '#fff0f6', border: 'none', borderRadius: 12 }}>
                  <Statistic
                    title={<Text style={{ fontSize: 12, color: '#667085' }}>技能</Text>}
                    value={stats?.skills ?? '-'}
                    prefix={<ThunderboltOutlined style={{ fontSize: 16, color: '#eb2f96' }} />}
                    valueStyle={{ fontSize: 22, fontWeight: 700, color: '#eb2f96' }}
                    loading={loading}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ background: '#f9f0ff', border: 'none', borderRadius: 12 }}>
                  <Statistic
                    title={<Text style={{ fontSize: 12, color: '#667085' }}>技能调用</Text>}
                    value={stats?.skill_calls ?? '-'}
                    prefix={<RobotOutlined style={{ fontSize: 16, color: '#722ed1' }} />}
                    valueStyle={{ fontSize: 22, fontWeight: 700, color: '#722ed1' }}
                    loading={loading}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ background: '#fffbe6', border: 'none', borderRadius: 12 }}>
                  <Statistic
                    title={<Text style={{ fontSize: 12, color: '#667085' }}>成本</Text>}
                    value={stats ? `¥${stats.total_cost_cny.toFixed(2)}` : '-'}
                    valueStyle={{ fontSize: 18, fontWeight: 700, color: '#d48806', whiteSpace: 'nowrap' }}
                    loading={loading}
                  />
                </Card>
              </Col>
            </Row>
          </div>

          {/* 配置摘要 */}
          <div style={{ padding: '16px 24px 24px' }}>
            <Descriptions
              column={2}
              size="small"
              bordered
              style={{ marginTop: 20 }}
              labelStyle={{ fontWeight: 500, color: '#667085' }}
            >
              <Descriptions.Item label="温度">{persona.temperature}</Descriptions.Item>
              <Descriptions.Item label="知识库">{persona.enable_knowledge ? '开' : '关'}</Descriptions.Item>
              <Descriptions.Item label="记忆工具">{persona.enable_memory ? '开' : '关'}</Descriptions.Item>
              <Descriptions.Item label="联网搜索">{persona.enable_web_search ? '开' : '关'}</Descriptions.Item>
              <Descriptions.Item label="MCP 工具">{persona.enable_mcp ? '开' : '关'}</Descriptions.Item>
              <Descriptions.Item label="角色记忆">{persona.memory_text ? `${persona.memory_text.length} 字` : '无'}</Descriptions.Item>
              <Descriptions.Item label="人设提示词" span={2}>
                <div style={{ maxHeight: 60, overflow: 'auto', whiteSpace: 'pre-wrap', fontSize: 12 }}>
                  {persona.system_prompt || '(空)'}
                </div>
              </Descriptions.Item>
            </Descriptions>
          </div>
        </div>
      )}
    </Modal>
  )
}
