import { useEffect, useState } from 'react'
import {
  Button,
  Input,
  Modal,
  Select,
  Slider,
  Space,
  Switch,
  Tabs,
  Tag,
  Tooltip,
  Upload,
  message as antdMessage,
} from 'antd'
import {
  CameraOutlined,
  CloseCircleFilled,
  DeleteOutlined,
  EditOutlined,
  ImportOutlined,
  PlusOutlined,
  ShoppingOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { chatApi } from '@/api/chat'
import { personaApi, type Persona, type PersonaPayload } from '@/api/personas'
import { skillApi, type Skill } from '@/api/skills'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'
import { useSkillStore } from '@/stores/skillStore'
import { AuthenticatedImage } from '@/components/AuthenticatedImage'
import { personaGradientCss, personaInitial } from './personaGradient'
import SkillEditModal from '../skill/SkillEditModal'
import MarketModal from './SkillMarketModal'
import GrowthPanel from '@/components/persona/GrowthPanel'
import PublishPersonaModal from '@/components/market/PublishPersonaModal'

interface Props {
  open: boolean
  persona: Persona | null // null = 新建
  onClose: () => void
  onSaved: () => void
}

export default function PersonaEditModal({ open, persona, onClose, onSaved }: Props) {
  // ── 基础 ──
  const [name, setName] = useState('')
  const [prompt, setPrompt] = useState('')
  const [temperature, setTemperature] = useState(0.7)
  const [avatarKey, setAvatarKey] = useState<string | null>(null)
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  // ── 角色记忆 ──
  const [memoryText, setMemoryText] = useState('')

  // ── 技能（当前角色的） ──
  const skillStore = useSkillStore()
  const [skillEditOpen, setSkillEditOpen] = useState(false)
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null)
  const [importingSkill, setImportingSkill] = useState(false)
  const [marketOpen, setMarketOpen] = useState(false)

  // ── 工具 ──
  const [enableKnowledge, setEnableKnowledge] = useState(true)
  const [enableMemory, setEnableMemory] = useState(true)
  const [enableWebSearch, setEnableWebSearch] = useState(false)
  const [enableMcp, setEnableMcp] = useState(false)
  const [mcpServerIds, setMcpServerIds] = useState<string[]>([])
  const [mcpServers, setMcpServers] = useState<{id:string,name:string}[]>([])
  const [toolKeys, setToolKeys] = useState<string[]>([])
  const [kbIds, setKbIds] = useState<string[]>([])

  // ── 上下文 ──
  const [conversationScope, setConversationScope] = useState<'shared' | 'isolated'>('shared')
  const [contextWindow, setContextWindow] = useState(20)

  // ── 风格 ──
  const [humanMode, setHumanMode] = useState(false)
  const [showAvatar, setShowAvatar] = useState(false)
  const [enableActiveRecall, setEnableActiveRecall] = useState(true)
  const [enableCrossSession, setEnableCrossSession] = useState(false)
  const [allowAgentCall, setAllowAgentCall] = useState(false)

  // ── 保存 ──
  const [saving, setSaving] = useState(false)
  const [optimizing, setOptimizing] = useState(false)

  const kbList = useKnowledgeBaseStore((s) => s.list)
  const ensureKbLoaded = useKnowledgeBaseStore((s) => s.ensureLoaded)

  // 重置表单
  useEffect(() => {
    if (open) {
      setName(persona?.name ?? '')
      setPrompt(persona?.system_prompt ?? '')
      setTemperature(persona?.temperature ?? 0.7)
      setAvatarKey(persona?.avatar_key ?? null)
      setAvatarUrl(persona?.avatar_url ?? null)
      setMemoryText(persona?.memory_text ?? '')
      setEnableKnowledge(persona?.enable_knowledge ?? true)
      setEnableMemory(persona?.enable_memory ?? true)
      setEnableWebSearch(persona?.enable_web_search ?? false)
      setEnableMcp(persona?.enable_mcp ?? false)
      setToolKeys(persona?.tool_keys ?? [])
      setKbIds(persona?.kb_ids ?? [])
      setConversationScope(persona?.conversation_scope ?? 'shared')
      setContextWindow(persona?.context_window ?? 20)
      setHumanMode(persona?.human_mode ?? false)
      setShowAvatar(persona?.show_avatar ?? false)
      setEnableActiveRecall(persona?.enable_active_recall ?? true)
      setEnableCrossSession(persona?.enable_cross_session ?? false)
      setMcpServerIds(persona?.mcp_server_ids ?? [])
      setAllowAgentCall(persona?.allow_agent_call ?? false)
      ensureKbLoaded()
      // 加载用户 MCP 服务器列表
      import('@/api/mcp').then(({ mcpApi }) => {
        mcpApi.list().then(({ data }) => {
          setMcpServers(data.map((s) => ({ id: s.id, name: s.name })))
        }).catch(() => {})
      })
      if (persona) skillStore.loadForPersona(persona.id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, persona])

  const pid = persona?.id ?? ''

  // 技能列表刷新
  const refreshSkills = () => {
    if (pid) skillStore.refresh(pid)
  }

  // 删除技能
  const deleteSkill = async (s: Skill) => {
    try {
      await skillApi.remove(pid, s.id)
      antdMessage.success('已删除')
      refreshSkills()
    } catch (e) {
      antdMessage.error((e as Error).message)
    }
  }

  // ZIP 导入
  const handleImport = async (file: File) => {
    if (!pid) return false
    setImportingSkill(true)
    try {
      await skillApi.importZip(pid, file)
      antdMessage.success('已导入')
      refreshSkills()
    } catch (e) {
      antdMessage.error((e as Error).message)
    } finally {
      setImportingSkill(false)
    }
    return false
  }

  // 头像上传
  const onUpload = async (file: File) => {
    setUploading(true)
    try {
      const { data } = await chatApi.uploadImage(file)
      setAvatarKey(data.file_key)
      setAvatarUrl(data.url)
    } catch (e) {
      antdMessage.error((e as Error).message)
    } finally {
      setUploading(false)
    }
    return false
  }

  // 保存
  const onSave = async () => {
    if (!name.trim()) {
      antdMessage.warning('请填写角色名')
      return
    }
    const payload: PersonaPayload = {
      name: name.trim(),
      avatar_key: avatarKey ?? '',
      system_prompt: prompt,
      temperature,
      memory_text: memoryText,
      tool_keys: toolKeys,
      enable_knowledge: enableKnowledge,
      enable_memory: enableMemory,
      enable_web_search: enableWebSearch,
      enable_mcp: enableMcp,
      mcp_server_ids: mcpServerIds,
      enable_active_recall: enableActiveRecall,
      enable_cross_session: enableCrossSession,
      kb_ids: kbIds,
      conversation_scope: conversationScope,
      context_window: contextWindow,
      human_mode: humanMode,
      show_avatar: showAvatar,
      allow_agent_call: allowAgentCall,
    }
    setSaving(true)
    try {
      if (persona) {
        await personaApi.update(persona.id, payload)
        antdMessage.success('已保存')
      } else {
        await personaApi.create(payload)
        antdMessage.success('已创建')
      }
      onSaved()
      onClose()
    } catch (e) {
      antdMessage.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const grad = personaGradientCss(name || '?')

  // Tabs
  const tabItems = [
    {
      key: 'basic',
      label: '基础',
      children: (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' as const }}>
          {/* 左：头像 */}
          <div style={{ flex: '0 0 120px', textAlign: 'center' as const }}>
            <Upload
              accept="image/*"
              showUploadList={false}
              beforeUpload={onUpload as never}
              disabled={uploading}
            >
              <div className="persona-upload" style={{ background: grad, margin: '0 auto' }}>
                {avatarUrl ? (
                  <AuthenticatedImage
                    src={avatarUrl}
                    alt="头像"
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                ) : (
                  <span className="persona-upload-initial">
                    {name.trim() ? personaInitial(name) : <CameraOutlined />}
                  </span>
                )}
                <div className="persona-upload-mask">
                  <CameraOutlined /> {uploading ? '上传中' : '上传头像'}
                </div>
              </div>
            </Upload>
            {avatarUrl && (
              <Button
                type="text" size="small" danger
                icon={<CloseCircleFilled />}
                onClick={() => { setAvatarKey(null); setAvatarUrl(null) }}
              >
                移除
              </Button>
            )}
          </div>
          {/* 右：名称/提示词/温度 */}
          <div style={{ flex: 1, minWidth: 280 }}>
            <div className="persona-field-label">角色名</div>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如：代码导师 / 周杰伦"
              maxLength={64}
            />
            <div className="persona-field-label" style={{ marginTop: 14 }}>
              <Space>
                <span>人设提示词</span>
                <Button
                  size="small" type="link"
                  icon={<ThunderboltOutlined />}
                  loading={optimizing}
                  onClick={async () => {
                    const raw = prompt.trim()
                    if (!raw) { antdMessage.warning('请先填写人设提示词'); return }
                    setOptimizing(true)
                    try {
                      antdMessage.info('提示词优化功能将在后续版本恢复')
                    } catch (e) {
                      antdMessage.error((e as Error).message)
                    } finally {
                      setOptimizing(false)
                    }
                  }}
                  style={{ padding: 0 }}
                >
                  优化
                </Button>
              </Space>
            </div>
            <Input.TextArea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              autoSize={{ minRows: 5, maxRows: 12 }}
              placeholder="描述这个角色的身份、说话风格、口头禅等"
              maxLength={20000}
            />
            <div className="persona-field-label" style={{ marginTop: 14 }}>
              温度（创造性）
            </div>
            <Slider
              min={0} max={2} step={0.1}
              value={temperature}
              onChange={setTemperature}
              marks={{ 0: '严谨', 1: '平衡', 2: '发散' }}
            />
          </div>
        </div>
      ),
    },
    {
      key: 'memory',
      label: '角色记忆',
      children: (
        <div>
          <div className="persona-field-tip" style={{ marginBottom: 8 }}>
            角色专属的 MEMORY.md 文件，Markdown 格式。会注入到每次对话的上下文中。
            可以在这里记录角色应该知道的关于用户的信息。
          </div>
          <Input.TextArea
            value={memoryText}
            onChange={(e) => setMemoryText(e.target.value)}
            autoSize={{ minRows: 8, maxRows: 20 }}
            placeholder={`# 关于用户\n- 用户偏好 Python，正在学 Rust\n- 不喜欢太啰嗦的解释\n\n# 上次对话\n- 聊到了微服务架构设计`}
            maxLength={50000}
          />
        </div>
      ),
    },
    {
      key: 'skills',
      label: '技能',
      children: (
        <div>
          <div className="persona-field-tip" style={{ marginBottom: 12 }}>
            技能会在切换到此角色时自动挂载。带脚本的技能会注册为 Agent 可调用的工具。调用次数越多的技能在市场中排名越高。
          </div>
          {/* 已有技能列表 */}
          {skillStore.list.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
              {skillStore.list.map((s) => (
                <div
                  key={s.id}
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '8px 12px', background: '#fafafa', borderRadius: 8,
                    border: '1px solid #f0f0f0',
                  }}
                >
                  <Space>
                    <span style={{ fontSize: 18 }}>{s.icon}</span>
                    <div>
                      <div style={{ fontWeight: 500 }}>{s.name}</div>
                      <div style={{ fontSize: 12, color: '#98A2B3' }}>
                        {s.description || s.source}
                        {s.call_count > 0 && ` · 调用 ${s.call_count} 次`}
                      </div>
                    </div>
                    {s.is_public && <Tag color="purple" style={{ margin: 0 }}>市场</Tag>}
                    {s.is_builtin && <Tag color="blue" style={{ margin: 0 }}>内置</Tag>}
                    {s.source === 'imported' && <Tag color="green" style={{ margin: 0 }}>导入</Tag>}
                  </Space>
                  <Space size={4}>
                    <Tooltip title="编辑">
                      <Button
                        type="text" size="small" icon={<EditOutlined />}
                        onClick={() => { setEditingSkill(s); setSkillEditOpen(true) }}
                      />
                    </Tooltip>
                    <Tooltip title="删除">
                      <Button
                        type="text" size="small" danger icon={<DeleteOutlined />}
                        onClick={() => deleteSkill(s)}
                      />
                    </Tooltip>
                  </Space>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: '#98A2B3', marginBottom: 16, textAlign: 'center', padding: 24 }}>
              还没有技能，创建一个、从 zip 导入或从市场添加
            </div>
          )}
          {/* 操作按钮 */}
          {pid ? (
            <div>
              <Space style={{ marginBottom: 8 }}>
                <Button
                  icon={<PlusOutlined />}
                  onClick={() => { setEditingSkill(null); setSkillEditOpen(true) }}
                >
                  新建技能
                </Button>
                <Upload
                  accept=".zip"
                  showUploadList={false}
                  beforeUpload={handleImport as never}
                  disabled={importingSkill}
                >
                  <Button icon={<ImportOutlined />} loading={importingSkill}>
                    导入 .soulskill.zip
                  </Button>
                </Upload>
                <Button
                  icon={<ImportOutlined />}
                  onClick={() => setMarketOpen(true)}
                >
                  技能市场
                </Button>
              </Space>
              <div style={{ fontSize: 12, color: '#98a2b3' }}>
                .soulskill.zip 内含 SKILL.md（YAML frontmatter + 提示词）+ 可选 scripts/ 目录
              </div>
            </div>
          ) : (
            <div style={{ color: '#98A2B3' }}>请先保存角色后再添加技能</div>
          )}
          {/* 技能编辑弹窗 */}
          {pid && (
            <SkillEditModal
              open={skillEditOpen}
              personaId={pid}
              skill={editingSkill}
              onClose={() => setSkillEditOpen(false)}
              onSaved={refreshSkills}
            />
          )}
          {/* 技能市场弹窗 */}
          <MarketModal
            open={marketOpen}
            personaId={pid}
            onClose={() => setMarketOpen(false)}
            onAdded={refreshSkills}
          />
        </div>
      ),
    },
    {
      key: 'tools',
      label: '工具',
      children: (
        <div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>🔍 知识库检索</span>
              <Switch checked={enableKnowledge} onChange={setEnableKnowledge} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>🧠 记忆工具</span>
              <Switch checked={enableMemory} onChange={setEnableMemory} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>🌐 联网搜索</span>
              <Switch checked={enableWebSearch} onChange={setEnableWebSearch} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>🕐 时间工具</span>
              <Switch defaultChecked disabled />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>📝 角色记忆工具</span>
              <Switch defaultChecked disabled />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>🔌 MCP 工具</span>
              <Switch checked={enableMcp} onChange={setEnableMcp} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>🤝 允许其他角色调用</span>
              <Switch checked={allowAgentCall} onChange={setAllowAgentCall} />
            </div>
            <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: -8, marginBottom: 8 }}>
              开启后，其他角色可把此角色当作工具调用（如"让代码审查官看一下这段代码"）
            </div>
            {enableMcp && (
              <div style={{ marginTop: 8 }}>
                <div className="persona-field-label">选用 MCP 服务（空=全部可用）</div>
                {mcpServers.length === 0 ? (
                  <div style={{ fontSize: 12, color: '#fa8c16' }}>
                    还没有 MCP 服务，先去「设置 → 工具配置 → MCP 服务」添加
                  </div>
                ) : (
                  <Select
                    mode="multiple"
                    value={mcpServerIds}
                    onChange={setMcpServerIds}
                    style={{ width: '100%' }}
                    placeholder="留空使用全部 MCP 服务"
                    allowClear
                    options={mcpServers.map((s) => ({ value: s.id, label: s.name }))}
                  />
                )}
              </div>
            )}

            <div style={{ marginTop: 8 }}>
              <div className="persona-field-label">默认知识库范围</div>
              <Select
                mode="multiple"
                value={kbIds}
                onChange={setKbIds}
                style={{ width: '100%' }}
                placeholder="留空=用户全部启用的库"
                allowClear
                options={kbList.map((k) => ({
                  value: k.id,
                  label: `${k.icon ?? '📚'} ${k.name}`,
                }))}
              />
            </div>
          </div>
        </div>
      ),
    },
    {
      key: 'context',
      label: '上下文',
      children: (
        <div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div>
              <div className="persona-field-label">对话历史模式</div>
              <Select
                value={conversationScope}
                onChange={setConversationScope}
                style={{ width: '100%' }}
                options={[
                  { value: 'shared', label: '共享 — 所有对话可见，切换角色不换对话列表' },
                  { value: 'isolated', label: '隔离 — 对话归属此角色，切换角色后只看该角色的对话' },
                ]}
              />
            </div>
            <div>
              <div className="persona-field-label">上下文窗口（历史轮数）</div>
              <Slider
                min={1} max={50} step={1}
                value={contextWindow}
                onChange={setContextWindow}
                marks={{ 1: '1', 10: '10', 20: '20', 50: '50' }}
              />
            </div>
          </div>
        </div>
      ),
    },
    {
      key: 'style',
      label: '风格',
      children: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>真人聊天模式（口语/多气泡/不写报告）</span>
            <Switch checked={humanMode} onChange={setHumanMode} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>显示头像</span>
            <Switch checked={showAvatar} onChange={setShowAvatar} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>主动记忆召回</span>
            <Switch checked={enableActiveRecall} onChange={setEnableActiveRecall} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>跨会话上下文</span>
            <Switch checked={enableCrossSession} onChange={setEnableCrossSession} />
          </div>
        </div>
      ),
    },
    // 成长 Tab — 仅编辑已有角色时显示
    ...(persona ? [{
      key: 'growth',
      label: '成长',
      children: <GrowthPanel personaId={persona.id} />,
    }] : []),
  ]

  const [publishOpen, setPublishOpen] = useState(false)

  return (
    <Modal
      open={open}
      onCancel={onClose}
      onOk={onSave}
      confirmLoading={saving}
      okText="保存"
      cancelText="取消"
      title={persona ? `编辑角色：${persona.name}` : '打造你的角色'}
      width={720}
      className="persona-modal"
      styles={{ body: { paddingTop: 0 } }}
      footer={(_, { OkBtn, CancelBtn }) => (
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <div>
            {persona && (
              <Button
                type="dashed"
                icon={<ShoppingOutlined />}
                onClick={() => setPublishOpen(true)}
              >
                {persona.is_listed ? '更新市场信息' : '发布到市场'}
              </Button>
            )}
          </div>
          <Space>
            <CancelBtn />
            <OkBtn />
          </Space>
        </div>
      )}
    >
      <Tabs items={tabItems} style={{ marginTop: 8 }} />
      {persona && (
        <PublishPersonaModal
          persona={persona}
          open={publishOpen}
          onClose={() => setPublishOpen(false)}
          onPublished={() => {
            setPublishOpen(false)
            onSaved?.()
          }}
        />
      )}
    </Modal>
  )
}
