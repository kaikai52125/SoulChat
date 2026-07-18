import { useEffect, useState } from 'react'
import { Empty, Pagination, Segmented, Skeleton, Typography } from 'antd'
import { personaDiaryApi, type DiaryEntry } from '@/api/personaDiary'
import { personaApi, type Persona } from '@/api/personas'
import DiaryCard from '@/components/diary/DiaryCard'

const { Title } = Typography

export default function DiaryPage() {
  const [personas, setPersonas] = useState<Persona[]>([])
  const [selectedPersona, setSelectedPersona] = useState<string | undefined>()
  const [diaries, setDiaries] = useState<DiaryEntry[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    personaApi.list(true).then((res: any) => setPersonas(res.data)).catch(() => {})
  }, [])

  useEffect(() => {
    setLoading(true)
    personaDiaryApi.listDiaries({
      persona_id: selectedPersona,
      page,
      page_size: 20,
    }).then((res) => {
      setDiaries(res.items)
      setTotal(res.total)
      // auto mark visible as read
      res.items.forEach(d => { if (!d.is_read) personaDiaryApi.markRead(d.id).catch(() => {}) })
    }).finally(() => setLoading(false))
  }, [selectedPersona, page])

  const personaMap = new Map(personas.map((p) => [p.id, p.name]))

  // Group diaries by date
  const grouped: Record<string, DiaryEntry[]> = {}
  for (const d of diaries) {
    const dateKey = d.diary_date || '未知日期'
    if (!grouped[dateKey]) grouped[dateKey] = []
    grouped[dateKey].push(d)
  }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '24px 16px' }}>
      <Title level={3} style={{ marginBottom: 16 }}>📔 角色日记</Title>

      {personas.length > 0 && (
        <Segmented
          value={selectedPersona}
          onChange={(val) => { setSelectedPersona(val as string | undefined); setPage(1) }}
          options={[
            { label: '全部', value: undefined as unknown as string },
            ...personas.map((p) => ({ label: p.name, value: p.id })),
          ]}
          style={{ marginBottom: 24 }}
          block
        />
      )}

      {loading ? (
        <div style={{ maxWidth: 800 }}>
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} active paragraph={{ rows: 3 }} style={{ marginBottom: 16 }} />
          ))}
        </div>
      ) : diaries.length === 0 ? (
        <Empty description="暂无日记，和角色聊聊天吧" />
      ) : (
        <>
          {Object.entries(grouped).map(([dateKey, entries]) => (
            <div key={dateKey} style={{ marginBottom: 24 }}>
              <Title level={5} type="secondary" style={{ marginBottom: 8 }}>
                {dateKey}
              </Title>
              {entries.map((d) => (
                <DiaryCard
                  key={d.id}
                  diary={d}
                  personaName={personaMap.get(d.persona_id) || undefined}
                />
              ))}
            </div>
          ))}
          <Pagination
            current={page}
            total={total}
            pageSize={20}
            onChange={setPage}
            style={{ textAlign: 'center', marginTop: 16 }}
          />
        </>
      )}
    </div>
  )
}
