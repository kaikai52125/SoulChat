import { useState } from 'react'
import { Modal, Select, Upload, message as antdMessage } from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import { personaApi, type Persona } from '@/api/personas'
import { skillApi } from '@/api/skills'

interface Props {
  open: boolean
  onClose: () => void
  onUploaded: () => void
}

export default function MarketUploadModal({ open, onClose, onUploaded }: Props) {
  const [personaId, setPersonaId] = useState('')
  const [personas, setPersonas] = useState<Persona[]>([])
  const [uploading, setUploading] = useState(false)

  const loadPersonas = async () => {
    try {
      const { data } = await personaApi.list()
      setPersonas(data)
      if (data.length > 0) {
        const active = data.find((p) => p.is_active)
        setPersonaId(active?.id ?? data[0].id)
      }
    } catch {
      // ignore
    }
  }

  // 弹窗打开时加载
  if (open && personas.length === 0) loadPersonas()

  const handleUpload = async (file: File) => {
    if (!personaId) {
      antdMessage.warning('请先选择一个角色')
      return false
    }
    setUploading(true)
    try {
      const { data: skill } = await skillApi.importZip(personaId, file)
      // 导入后自动设为公开
      await skillApi.update(personaId, skill.id, { is_public: true })
      antdMessage.success(`已上传「${skill.name}」到市场`)
      onUploaded()
      onClose()
    } catch (e) {
      antdMessage.error((e as Error).message)
    } finally {
      setUploading(false)
    }
    return false
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      title="上传到技能市场"
      width={480}
    >
      <div style={{ marginBottom: 16 }}>
        <div className="persona-field-label">归属角色</div>
        <Select
          value={personaId || undefined}
          onChange={setPersonaId}
          style={{ width: '100%' }}
          placeholder="选择角色"
          options={personas.map((p) => ({ value: p.id, label: p.name }))}
        />
        <div className="persona-field-tip" style={{ marginTop: 4 }}>
          技能归属于此角色，发布后其他用户可搜索并使用
        </div>
      </div>

      <Upload.Dragger
        accept=".zip"
        showUploadList={false}
        beforeUpload={handleUpload as never}
        disabled={uploading || !personaId}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">点击或拖拽 .soulskill.zip 到此区域</p>
        <p className="ant-upload-hint">
          上传后自动发布到技能市场
        </p>
      </Upload.Dragger>
    </Modal>
  )
}
