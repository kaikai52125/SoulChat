import { useEffect, useState } from 'react'
import { Button, Descriptions, List, Modal, Rate, Space, Spin, Tag, Typography, message } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import { personaMarketApi, type MarketDetail } from '@/api/personaMarket'

const { Text, Paragraph } = Typography

interface Props {
  listingId: string | null
  open: boolean
  onClose: () => void
  onImported?: () => void
}

export default function PersonaMarketDetailModal({ listingId, open, onClose, onImported }: Props) {
  const [detail, setDetail] = useState<MarketDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [importing, setImporting] = useState(false)

  useEffect(() => {
    if (listingId && open) {
      setLoading(true)
      personaMarketApi.getDetail(listingId)
        .then(setDetail)
        .catch(() => message.error('加载失败'))
        .finally(() => setLoading(false))
    }
  }, [listingId, open])

  const handleImport = async () => {
    if (!listingId) return
    setImporting(true)
    try {
      await personaMarketApi.importPersona(listingId)
      message.success('已添加到你的角色列表')
      onImported?.()
      onClose()
    } catch {
      message.error('导入失败')
    } finally {
      setImporting(false)
    }
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={[
        <Button key="close" onClick={onClose}>关闭</Button>,
        <Button key="import" type="primary" icon={<DownloadOutlined />} loading={importing} onClick={handleImport}>
          一键导入到我的角色
        </Button>,
      ]}
      title={detail ? `${detail.icon} ${detail.market_name}` : '角色详情'}
      width={640}
    >
      {loading ? (
        <Spin style={{ display: 'block', textAlign: 'center', padding: 40 }} />
      ) : detail ? (
        <>
          <Paragraph style={{ marginBottom: 16 }}>{detail.market_description}</Paragraph>

          <Space wrap style={{ marginBottom: 16 }}>
            {(detail.tags || []).map((t) => <Tag key={t} color="blue">{t}</Tag>)}
          </Space>

          <Descriptions size="small" column={2} style={{ marginBottom: 16 }}>
            <Descriptions.Item label="评分">⭐ {detail.rating_avg} ({detail.rating_count} 评价)</Descriptions.Item>
            <Descriptions.Item label="下载">📥 {detail.downloads.toLocaleString()}</Descriptions.Item>
            <Descriptions.Item label="版本">{detail.version}</Descriptions.Item>
            {detail.changelog && <Descriptions.Item label="更新日志">{detail.changelog}</Descriptions.Item>}
          </Descriptions>

          {detail.persona_snapshot?.skills && detail.persona_snapshot.skills.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <Text strong>包含技能 ({detail.persona_snapshot.skills.length})</Text>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 4 }}>
                {detail.persona_snapshot.skills.map((s, i) => (
                  <Tag key={i} color="blue" style={{ padding: '4px 8px' }}>{s.icon} {s.name}</Tag>
                ))}
              </div>
            </div>
          )}

          {detail.persona_snapshot?.mcp_servers && detail.persona_snapshot.mcp_servers.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <Text strong>需要 MCP 服务 ({detail.persona_snapshot.mcp_servers.length})</Text>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 4 }}>
                {detail.persona_snapshot.mcp_servers.map((m, i) => (
                  <Text key={i} type="secondary" style={{ fontSize: 12 }}>🔌 {m.name}</Text>
                ))}
              </div>
              <Text type="secondary" style={{ fontSize: 11, marginTop: 4 }}>导入后需自行配置同名 MCP 服务才能使用</Text>
            </div>
          )}

          {detail.persona_snapshot?.system_prompt && (
            <div style={{ marginBottom: 16 }}>
              <Text strong>角色人设预览</Text>
              <Paragraph
                type="secondary"
                style={{
                  background: '#fafafa',
                  padding: 12,
                  borderRadius: 8,
                  maxHeight: 200,
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                  fontSize: 13,
                }}
              >
                {detail.persona_snapshot.system_prompt}
              </Paragraph>
            </div>
          )}

          {detail.reviews.length > 0 && (
            <>
              <Text strong style={{ display: 'block', marginBottom: 8 }}>用户评价</Text>
              <List
                size="small"
                dataSource={detail.reviews}
                renderItem={(r) => (
                  <List.Item>
                    <Space direction="vertical" size={2} style={{ width: '100%' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Rate disabled value={r.rating} count={5} style={{ fontSize: 12 }} />
                        <Text type="secondary" style={{ fontSize: 11 }}>{r.user_name || '匿名'}</Text>
                      </div>
                      {r.comment && <Text style={{ fontSize: 13 }}>{r.comment}</Text>}
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {r.created_at ? new Date(r.created_at).toLocaleDateString('zh-CN') : ''}
                      </Text>
                    </Space>
                  </List.Item>
                )}
              />
            </>
          )}
        </>
      ) : null}
    </Modal>
  )
}
