import { useState } from 'react'
import { Button, Typography, message } from 'antd'
import { DownloadOutlined, StarFilled, StarOutlined } from '@ant-design/icons'
import { personaMarketApi, type MarketCard as MarketCardType } from '@/api/personaMarket'

const { Text, Paragraph } = Typography

const CARD_COLORS = [
  'linear-gradient(135deg, #667eea, #764ba2)',
  'linear-gradient(135deg, #f093fb, #f5576c)',
  'linear-gradient(135deg, #4facfe, #00f2fe)',
  'linear-gradient(135deg, #43e97b, #38f9d7)',
  'linear-gradient(135deg, #fa709a, #fee140)',
  'linear-gradient(135deg, #a18cd1, #fbc2eb)',
  'linear-gradient(135deg, #fccb90, #d57eeb)',
  'linear-gradient(135deg, #667eea, #f5576c)',
]
function pickColor(id: string) {
  let h = 0; for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0
  return CARD_COLORS[Math.abs(h) % CARD_COLORS.length]
}

interface Props { item: MarketCardType; onImported?: () => void }

export default function PersonaMarketCard({ item, onImported }: Props) {
  const [importing, setImporting] = useState(false)
  const [myRating, setMyRating] = useState(0)
  const [hoverStar, setHoverStar] = useState(0)

  const showRating = myRating > 0 ? myRating : (item.rating_avg || 0)
  const showCount = Math.max(item.rating_count, myRating > 0 ? 1 : 0)
  const stars = [1, 2, 3, 4, 5]
  const active = hoverStar > 0 ? hoverStar : Math.round(showRating)

  const doRate = (val: number) => {
    personaMarketApi.addReview(item.id, val)
      .then(() => { message.success('评价已提交'); setMyRating(val) })
      .catch(() => message.error('评价失败'))
  }

  const doImport = (e: React.MouseEvent) => {
    e.stopPropagation()
    setImporting(true)
    personaMarketApi.importPersona(item.id)
      .then(() => { message.success(`「${item.market_name}」已导入`); onImported?.() })
      .catch(() => message.error('导入失败'))
      .finally(() => setImporting(false))
  }

  return (
    <div style={{ borderRadius: 16, overflow: 'hidden', background: '#fff', border: '1px solid #f1f5f9', boxShadow: '0 1px 3px rgba(0,0,0,0.04)', transition: 'transform 0.2s, box-shadow 0.2s', cursor: 'pointer', width: '100%', display: 'flex', flexDirection: 'column' }}
      onMouseEnter={e => { const t = e.currentTarget as HTMLElement; t.style.transform = 'translateY(-3px)'; t.style.boxShadow = '0 8px 30px rgba(0,0,0,0.08)' }}
      onMouseLeave={e => { const t = e.currentTarget as HTMLElement; t.style.transform = ''; t.style.boxShadow = '' }}>
      <div style={{ height: 100, background: pickColor(item.id), display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
        <div style={{ width: 52, height: 52, borderRadius: 16, background: 'rgba(255,255,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 28 }}>{item.icon || '🤖'}</div>
        {showRating > 0 && (
          <div style={{ position: 'absolute', top: 10, right: 12, display: 'flex', alignItems: 'center', gap: 3, background: 'rgba(0,0,0,0.35)', borderRadius: 8, padding: '2px 8px', color: '#fff', fontSize: 12, fontWeight: 600 }}>
            <StarFilled style={{ color: '#fbbf24', fontSize: 11 }} /> {showRating.toFixed(1)}
          </div>
        )}
      </div>
      <div style={{ padding: '14px 16px 12px', flex: 1, display: 'flex', flexDirection: 'column' }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a', marginBottom: 4 }}>{item.market_name}</div>
          <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 8, fontSize: 12, color: '#64748b', lineHeight: 1.5 }}>{item.market_description}</Paragraph>
          <div style={{ marginBottom: 8, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {(item.tags || []).slice(0, 3).map((t: string) => <span key={t} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 6, background: '#f1f5f9', color: '#475569' }}>{t}</span>)}
          </div>
          {(item.skills && item.skills.length > 0) && (
            <div style={{ marginBottom: 8, display: 'flex', flexWrap: 'wrap', gap: 4, alignItems: 'center' }}>
              {item.skills.slice(0, 3).map((s, i) => (
                <span key={i} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 6, background: '#ede9fe', color: '#7c3aed' }}>{s.icon} {s.name}</span>
              ))}
              {item.skills.length > 3 && <span style={{ fontSize: 10, color: '#94a3b8' }}>+{item.skills.length - 3}</span>}
            </div>
          )}
          {(item.mcp_servers && item.mcp_servers.length > 0) && (
            <div style={{ marginBottom: 8, display: 'flex', flexWrap: 'wrap', gap: 4, alignItems: 'center' }}>
              {item.mcp_servers.slice(0, 2).map((m, i) => (
                <span key={i} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 6, background: '#fef3c7', color: '#92400e' }}>🔌 {m.name}</span>
              ))}
              {item.mcp_servers.length > 2 && <span style={{ fontSize: 10, color: '#94a3b8' }}>+{item.mcp_servers.length - 2}</span>}
            </div>
          )}
        </div>
        <div style={{ marginTop: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div onClick={e => e.stopPropagation()} onMouseLeave={() => setHoverStar(0)}>
              {stars.map(i => (
                <span key={i} onMouseEnter={() => setHoverStar(i)} onClick={() => doRate(i)}
                  style={{ fontSize: 16, cursor: 'pointer', color: i <= active ? '#fbbf24' : '#e2e8f0', marginRight: 2 }}>
                  {i <= active ? <StarFilled /> : <StarOutlined />}
                </span>
              ))}
              <Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>({showCount})</Text>
            </div>
            <Text type="secondary" style={{ fontSize: 11 }}>📥 {item.downloads.toLocaleString()}</Text>
          </div>
          <Button type="primary" block icon={<DownloadOutlined />} loading={importing} onClick={doImport} style={{ borderRadius: 10, height: 34, fontWeight: 600 }}>一键导入</Button>
        </div>
      </div>
    </div>
  )
}
