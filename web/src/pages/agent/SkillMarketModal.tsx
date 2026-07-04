import { useEffect, useState } from 'react'
import { Button, Empty, Modal, Select, Space, Tag, message as antdMessage } from 'antd'
import { DownloadOutlined, FireOutlined } from '@ant-design/icons'
import { skillApi, type Skill } from '@/api/skills'
import { personaApi, type Persona } from '@/api/personas'

interface Props {
  open: boolean
  personaId: string
  onClose: () => void
  onAdded: () => void
}

export default function SkillMarketModal({ open, personaId, onClose, onAdded }: Props) {
  const [list, setList] = useState<Skill[]>([])
  const [adding, setAdding] = useState<string | null>(null)
  const [targetPersona, setTargetPersona] = useState(personaId)
  const [personas, setPersonas] = useState<Persona[]>([])

  const load = async () => {
    try {
      const { data } = await skillApi.marketplace(50, 0)
      setList(data)
    } catch (e) {
      antdMessage.error((e as Error).message)
    }
  }

  useEffect(() => {
    if (open) {
      load()
      // 加载角色列表供 fork 选择
      personaApi.list().then(({ data }) => setPersonas(data)).catch(() => {})
      setTargetPersona(personaId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const onFork = async (s: Skill) => {
    setAdding(s.id)
    try {
      await skillApi.fork(s.id, targetPersona)
      antdMessage.success(`已添加「${s.name}」到角色`)
      onAdded()
    } catch (e) {
      antdMessage.error((e as Error).message)
    } finally {
      setAdding(null)
    }
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      title="技能市场"
      width={640}
      styles={{ body: { maxHeight: '60vh', overflowY: 'auto', paddingTop: 4 } }}
    >
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 13, color: '#667085' }}>添加到角色：</span>
        <Select
          size="small"
          value={targetPersona}
          onChange={setTargetPersona}
          style={{ width: 200 }}
          options={personas.map((p) => ({ value: p.id, label: p.name }))}
        />
      </div>

      {list.length === 0 ? (
        <Empty description="市场暂无公开技能" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {list.map((s) => (
            <div
              key={s.id}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '12px 14px', background: '#fff', borderRadius: 10,
                border: '1px solid #ececf0',
              }}
            >
              <Space>
                <span style={{ fontSize: 22 }}>{s.icon}</span>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{s.name}</div>
                  <div style={{ fontSize: 12, color: '#98A2B3', marginTop: 2 }}>
                    {s.description || '暂无简介'}
                  </div>
                  <Space size={4} style={{ marginTop: 4 }}>
                    {s.call_count > 0 && (
                      <Tag icon={<FireOutlined />} color="orange" style={{ margin: 0, fontSize: 11 }}>
                        {s.call_count} 次调用
                      </Tag>
                    )}
                    {s.source === 'imported' && (
                      <Tag color="green" style={{ margin: 0, fontSize: 11 }}>导入</Tag>
                    )}
                  </Space>
                </div>
              </Space>
              <Button
                type="primary" size="small" ghost
                icon={<DownloadOutlined />}
                loading={adding === s.id}
                onClick={() => onFork(s)}
              >
                添加到角色
              </Button>
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}
