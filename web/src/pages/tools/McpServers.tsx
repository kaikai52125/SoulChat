import { useEffect, useState } from 'react'
import {
  Badge, Button, Card, Drawer, Empty, Form, Input, List, Modal, Popconfirm,
  Select, Space, Switch, Table, Tag, Typography, message,
} from 'antd'
import {
  ApiOutlined, DeleteOutlined, EditOutlined, PlusOutlined,
  ShopOutlined, SyncOutlined, ThunderboltOutlined, UnorderedListOutlined,
} from '@ant-design/icons'
import {
  mcpApi, type McpAuthType, type McpServer, type McpServerInput,
  type McpToolMeta, type McpTransport,
} from '@/api/mcp'

const { Text, Paragraph } = Typography

const STATUS_BADGE: Record<string, { status: 'success' | 'error' | 'default'; text: string }> = {
  ok: { status: 'success', text: '正常' },
  error: { status: 'error', text: '异常' },
  unknown: { status: 'default', text: '未测试' },
}

interface FormValues {
  name: string; transport: McpTransport; url: string; auth_type: McpAuthType
  token?: string; header?: string; key?: string
}

interface BuiltinMcp { key: string; name: string; description: string; icon: string; transport: string; auth_type: string; url_template: string; tools: McpToolMeta[] }

export default function McpServers() {
  const [servers, setServers] = useState<McpServer[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<McpServer | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [form] = Form.useForm<FormValues>()
  const authType = Form.useWatch('auth_type', form)
  const [toolsDrawer, setToolsDrawer] = useState<McpServer | null>(null)
  const [marketOpen, setMarketOpen] = useState(false)
  const [marketList, setMarketList] = useState<BuiltinMcp[]>([])

  const load = async () => { setLoading(true); try { const { data } = await mcpApi.list(); setServers(data) } catch (e) { message.error((e as Error).message) } finally { setLoading(false) } }
  useEffect(() => { load() }, [])

  const openCreate = () => { setEditing(null); setModalOpen(true) }
  const openEdit = (s: McpServer) => { setEditing(s); setModalOpen(true) }

  const onModalOpenChange = (open: boolean) => {
    if (!open) return
    if (editing) {
      form.setFieldsValue({ name: editing.name, transport: editing.transport, url: editing.url, auth_type: editing.auth_type, token: undefined, header: undefined, key: undefined })
    } else {
      form.resetFields(); form.setFieldsValue({ transport: 'streamable_http', auth_type: 'none' })
    }
  }

  const buildPayload = (v: FormValues): McpServerInput => {
    let auth_config: Record<string, string> | null = null
    if (v.auth_type === 'bearer' && v.token) auth_config = { token: v.token }
    if (v.auth_type === 'api_key' && v.key) auth_config = { header: v.header || 'X-API-Key', key: v.key }
    return { name: v.name, transport: v.transport, url: v.url, auth_type: v.auth_type, auth_config }
  }

  const onSubmit = async () => {
    const v = await form.validateFields(); const payload = buildPayload(v)
    try {
      if (editing && editing.id) { await mcpApi.update(editing.id, payload); message.success('已保存') }
      else { await mcpApi.create(payload); message.success('已添加') }
      setModalOpen(false); load()
    } catch (e) { message.error((e as Error).message) }
  }

  const onTest = async (s: McpServer) => { setBusy(s.id); try { const { data } = await mcpApi.test(s.id); data.success ? message.success(data.message) : message.error(data.message); load() } catch (e) { message.error((e as Error).message) } finally { setBusy(null) } }
  const onSync = async (s: McpServer) => { setBusy(s.id); try { await mcpApi.sync(s.id); message.success('已同步工具清单'); load() } catch (e) { message.error((e as Error).message) } finally { setBusy(null) } }
  const onToggle = async (s: McpServer, enabled: boolean) => { try { await mcpApi.toggle(s.id, enabled); setServers((prev) => prev.map((x) => (x.id === s.id ? { ...x, enabled } : x))) } catch (e) { message.error((e as Error).message) } }
  const onDelete = async (s: McpServer) => { try { await mcpApi.remove(s.id); message.success('已删除'); load() } catch (e) { message.error((e as Error).message) } }

  const openMarket = async () => { setMarketOpen(true); try { const { data } = await mcpApi.builtins(); setMarketList(data) } catch { } }

  const onAddBuiltin = (tpl: BuiltinMcp) => {
    setMarketOpen(false)
    const s: McpServer = { id: '', name: tpl.name, transport: tpl.transport as McpTransport, url: tpl.url_template || '', auth_type: tpl.auth_type as McpAuthType, auth_masked: '', enabled: true, status: 'unknown', last_error: null, tools_cache: tpl.tools as McpToolMeta[], synced_at: null, created_at: '' }
    setEditing(s); setModalOpen(true)
  }

  const toolColumns = [{ title: '名称', dataIndex: 'name', key: 'name', width: 240, render: (name: string) => <Tag color="blue">{name}</Tag> }, { title: '描述', dataIndex: 'description', key: 'description', render: (desc: string) => desc ? <Text style={{ fontSize: 13 }}>{desc}</Text> : <Text type="secondary" style={{ fontSize: 13 }}>（无描述）</Text> }]

  return (
    <Card className="mcp-servers-card" title={<Space><ApiOutlined />MCP 服务</Space>} loading={loading}
      extra={<Space><Button icon={<ShopOutlined />} onClick={openMarket}>MCP 市场</Button><Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>添加服务</Button></Space>}>
      <Paragraph type="secondary" style={{ marginTop: -8 }}>接入外部 MCP 服务，同步其工具后加入角色 Agent 可调用范围。</Paragraph>
      {servers.length === 0 ? <Empty description="暂无 MCP 服务" /> : (
        <List itemLayout="vertical" dataSource={servers} renderItem={(s) => {
          const badge = STATUS_BADGE[s.status] || STATUS_BADGE.unknown; const toolCount = s.tools_cache?.length ?? 0
          return <List.Item actions={[
            <Button key="tools" size="small" icon={<UnorderedListOutlined />} disabled={toolCount === 0} onClick={() => setToolsDrawer(s)}>工具清单（{toolCount}）</Button>,
            <Button key="test" size="small" icon={<ThunderboltOutlined />} loading={busy === s.id} onClick={() => onTest(s)}>测试连接</Button>,
            <Button key="sync" size="small" icon={<SyncOutlined />} loading={busy === s.id} onClick={() => onSync(s)}>同步工具</Button>,
            <Button key="edit" size="small" icon={<EditOutlined />} onClick={() => openEdit(s)}>编辑</Button>,
            <Popconfirm key="del" title="确认删除？" onConfirm={() => onDelete(s)}><Button size="small" danger icon={<DeleteOutlined />}>删除</Button></Popconfirm>,
            <Switch key="sw" checked={s.enabled} onChange={(v) => onToggle(s, v)} checkedChildren="启用" unCheckedChildren="停用" />,
          ]}>
            <List.Item.Meta title={<Space><Badge status={badge.status} text={s.name} /><Tag>{s.transport === 'sse' ? 'SSE' : 'HTTP'}</Tag>{s.auth_type !== 'none' && <Tag color="blue">{s.auth_type === 'bearer' ? 'Bearer' : 'API Key'}</Tag>}</Space>}
              description={<Space direction="vertical" size={2}><Text type="secondary" style={{ fontSize: 12 }}>{s.url}</Text>{toolCount === 0 && <Text type="secondary" style={{ fontSize: 12 }}>尚未同步工具</Text>}{s.status === 'error' && s.last_error && <Text type="danger" style={{ fontSize: 12 }}>{s.last_error}</Text>}</Space>} />
          </List.Item>
        }}/>
      )}
      <Drawer title={toolsDrawer ? `${toolsDrawer.name} · 工具清单` : '工具清单'} open={!!toolsDrawer} onClose={() => setToolsDrawer(null)} width={560}>
        <Table<McpToolMeta> rowKey="name" size="small" columns={toolColumns} dataSource={toolsDrawer?.tools_cache ?? []} pagination={false} />
      </Drawer>

      {/* MCP 市场弹窗 */}
      <Modal title="MCP 市场" open={marketOpen} onCancel={() => setMarketOpen(false)} footer={null} width={600} styles={{ body: { maxHeight: '60vh', overflowY: 'auto', paddingTop: 4 } }}>
        {marketList.length === 0 ? <Empty description="暂无可用模板" image={Empty.PRESENTED_IMAGE_SIMPLE} /> : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {marketList.map((m) => (
              <div key={m.key} style={{ display:'flex',alignItems:'flex-start',justifyContent:'space-between',padding:'12px 14px',background:'#fff',borderRadius:10,border:'1px solid #ececf0',gap:12 }}>
                <div style={{ flex:1,minWidth:0 }}><Space><span style={{fontSize:24,lineHeight:1}}>{m.icon}</span><div><div style={{fontWeight:600,fontSize:14}}>{m.name}</div><div style={{fontSize:12,color:'#98A2B3',marginTop:2}}>{m.description}</div></div></Space></div>
                <Button type="primary" size="small" ghost onClick={() => onAddBuiltin(m)} style={{flexShrink:0}}>添加</Button>
              </div>
            ))}
          </div>
        )}
      </Modal>

      <Modal title={editing ? '编辑 MCP 服务' : '添加 MCP 服务'} open={modalOpen} onOk={onSubmit} onCancel={() => setModalOpen(false)} afterOpenChange={onModalOpenChange} okText="保存" cancelText="取消">
        <Form form={form} layout="vertical">
          <Form.Item label="服务名称" name="name" rules={[{ required: true }]} extra="用于区分不同服务，会作为工具名前缀"><Input placeholder="例如：cloudflare-docs" /></Form.Item>
          <Form.Item label="传输类型" name="transport" rules={[{ required: true }]}><Select options={[{ value: 'streamable_http', label: 'Streamable HTTP' }, { value: 'sse', label: 'SSE' }]} /></Form.Item>
          <Form.Item label="服务地址 URL" name="url" rules={[{ required: true }]}><Input placeholder="https://example.com/sse" /></Form.Item>
          <Form.Item label="认证方式" name="auth_type" rules={[{ required: true }]}><Select options={[{ value: 'none', label: '无' }, { value: 'bearer', label: 'Bearer Token' }, { value: 'api_key', label: 'API Key' }]} /></Form.Item>
          {authType === 'bearer' && <Form.Item label="Token" name="token" extra={editing ? '留空表示不修改' : undefined} rules={editing ? [] : [{ required: true }]}><Input.Password placeholder="Bearer Token" /></Form.Item>}
          {authType === 'api_key' && <><Form.Item label="请求头名称" name="header"><Input placeholder="X-API-Key" /></Form.Item><Form.Item label="Key" name="key" extra={editing ? '留空表示不修改' : undefined} rules={editing ? [] : [{ required: true }]}><Input.Password placeholder="API Key" /></Form.Item></>}
        </Form>
      </Modal>
    </Card>
  )
}
