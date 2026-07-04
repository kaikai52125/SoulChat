import { useEffect, useState } from 'react'
import { Empty, Modal, Spin, Typography, message } from 'antd'
import {
  ExclamationCircleFilled,
  EditOutlined,
  PlusOutlined,
  ShopOutlined,
  TeamOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { personaApi, type Persona } from '@/api/personas'
import {
  personaGroupApi,
  type BuiltinGroup,
  type PersonaGroup,
} from '@/api/personaGroups'
import GroupMemberAvatars from '@/components/GroupMemberAvatars'
import PersonaCard from './agent/PersonaCard'
import PersonaEditModal from './agent/PersonaEditModal'
import PersonaGroupEditModal from './agent/PersonaGroupEditModal'
import MarketUploadModal from './agent/MarketUploadModal'
import MarketBrowseModal from './agent/MarketBrowseModal'
import PersonaDetailModal from './agent/PersonaDetailModal'

export default function AgentConfigPage() {
  const navigate = useNavigate()
  const [personas, setPersonas] = useState<Persona[]>([])
  const [groups, setGroups] = useState<PersonaGroup[]>([])
  const [builtins, setBuiltins] = useState<BuiltinGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [activatingId, setActivatingId] = useState<string | null>(null)
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<Persona | null>(null)
  const [groupEditOpen, setGroupEditOpen] = useState(false)
  const [editingGroup, setEditingGroup] = useState<PersonaGroup | null>(null)
  const [marketUploadOpen, setMarketUploadOpen] = useState(false)
  const [marketBrowseOpen, setMarketBrowseOpen] = useState(false)
  const [detailPersona, setDetailPersona] = useState<Persona | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await personaApi.list()
      setPersonas(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
    loadGroups()
  }

  const loadGroups = async () => {
    try {
      const [{ data: g }, { data: b }] = await Promise.all([
        personaGroupApi.list(),
        personaGroupApi.listBuiltins(),
      ])
      setGroups(g)
      setBuiltins(b)
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onActivate = async (p: Persona) => {
    setActivatingId(p.id)
    try {
      await personaApi.activate(p.id)
      message.success(`已切换为「${p.name}」`)
      load()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setActivatingId(null)
    }
  }

  const onDelete = (p: Persona) => {
    Modal.confirm({
      title: `确定要删除「${p.name}」吗？`,
      icon: <ExclamationCircleFilled />,
      content: '删除后无法恢复。该角色的技能也会被删除。',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await personaApi.remove(p.id)
          message.success('已删除')
          load()
        } catch (e) {
          message.error((e as Error).message)
        }
      },
    })
  }

  const onAddBuiltin = async (key: string) => {
    setBusyKey(key)
    try {
      await personaGroupApi.addBuiltin(key)
      message.success('已添加场景')
      load()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setBusyKey(null)
    }
  }

  if (loading) return <Spin style={{ display: 'block', marginTop: 80 }} />

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      {/* ===== 单个角色 ===== */}
      <div className="persona-page-header">
        <Typography.Title level={4} style={{ margin: 0 }}>
          我的角色
        </Typography.Title>
        <button
          className="btn-silk-plain"
          onClick={() => { setEditing(null); setEditOpen(true) }}
        >
          <PlusOutlined />
        </button>
      </div>

      {personas.length === 0 ? (
        <Empty
          description="还没有角色，点击 + 创建第一个"
          style={{ padding: '40px 0' }}
        />
      ) : (
        <div className="persona-card-grid" style={{ marginBottom: 40 }}>
          {personas.map((p, i) => (
            <PersonaCard
              key={p.id}
              index={i}
              persona={p}
              activating={activatingId === p.id}
              onActivate={() => onActivate(p)}
              onEdit={() => { setEditing(p); setEditOpen(true) }}
              onDelete={() => onDelete(p)}
              onClick={(p) => setDetailPersona(p)}
            />
          ))}
        </div>
      )}

      {/* ===== 角色卡组（场景）===== */}
      <div className="persona-page-header">
        <Typography.Title level={4} style={{ margin: 0 }}>
          角色卡组
        </Typography.Title>
        <button
          className="btn-silk-plain"
          onClick={() => { setEditingGroup(null); setGroupEditOpen(true) }}
        >
          <PlusOutlined />
        </button>
      </div>

      {builtins.length === 0 && groups.length === 0 ? (
        <Empty
          description="暂无场景"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          style={{ padding: '24px 0' }}
        />
      ) : (
        <>
          {/* 内置场景 */}
          {builtins.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <div className="persona-section-title">
                内置场景
              </div>
              <div className="persona-card-grid">
                {builtins.map((b) => (
                  <div key={b.key} className="persona-scene-card">
                    <div className="persona-scene-head">
                      <div className="persona-scene-icon">{b.icon}</div>
                      <div className="persona-scene-info">
                        <div className="persona-scene-name">{b.name}</div>
                        <div className="persona-scene-desc">{b.description}</div>
                      </div>
                    </div>
                    <div className="persona-scene-actions">
                      <GroupMemberAvatars members={b.members} size={24} />
                      <button
                        className="btn-silk-primary"
                        disabled={busyKey === b.key}
                        onClick={() => onAddBuiltin(b.key)}
                      >
                        {busyKey === b.key ? '添加中…' : '一键添加'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 自定义卡组 */}
          {groups.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <div className="persona-section-title">
                我的卡组
              </div>
              <div className="persona-card-grid">
                {groups.map((g) => (
                  <div key={g.id} className="persona-scene-card">
                    <div className="persona-scene-head">
                      <div className="persona-scene-icon">{g.icon || '👥'}</div>
                      <div className="persona-scene-info">
                        <div className="persona-scene-name">{g.name}</div>
                        <div className="persona-scene-desc">
                          {g.members?.length ?? 0} 个角色
                        </div>
                      </div>
                    </div>
                    <div className="persona-scene-actions">
                      <GroupMemberAvatars members={g.members} size={24} />
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button
                          className="btn-silk-primary"
                          onClick={() => navigate(`/group-chat?group_id=${g.id}`)}
                        >
                          <TeamOutlined /> 开聊
                        </button>
                        <button
                          className="btn-silk-plain"
                          onClick={() => { setEditingGroup(g); setGroupEditOpen(true) }}
                        >
                          <EditOutlined />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* ===== 技能市场 ===== */}
      <div style={{ marginTop: 40 }}>
        <div className="persona-page-header">
          <Typography.Title level={4} style={{ margin: 0 }}>
            技能市场
          </Typography.Title>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="btn-silk-primary"
              onClick={() => setMarketUploadOpen(true)}
            >
              <UploadOutlined /> 上传到市场
            </button>
            <button
              className="btn-silk-plain"
              onClick={() => setMarketBrowseOpen(true)}
            >
              <ShopOutlined />
            </button>
          </div>
        </div>
        <div className="persona-field-tip" style={{ marginBottom: 8 }}>
          上传 .soulskill.zip 到技能市场，所有用户都可以将你的技能添加到自己的角色中
        </div>
      </div>

      <PersonaEditModal
        open={editOpen}
        persona={editing}
        onClose={() => setEditOpen(false)}
        onSaved={() => load()}
      />
      <PersonaGroupEditModal
        open={groupEditOpen}
        group={editingGroup}
        onClose={() => setGroupEditOpen(false)}
        onSaved={load}
      />
      <MarketUploadModal
        open={marketUploadOpen}
        onClose={() => setMarketUploadOpen(false)}
        onUploaded={() => load()}
      />
      <MarketBrowseModal
        open={marketBrowseOpen}
        onClose={() => setMarketBrowseOpen(false)}
      />
      <PersonaDetailModal
        open={!!detailPersona}
        persona={detailPersona}
        onClose={() => setDetailPersona(null)}
      />
    </div>
  )
}
