import { useCallback, useEffect, useState } from 'react'
import { Empty, Input, Pagination, Segmented, Skeleton, Space, Typography } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { personaMarketApi, type MarketCard } from '@/api/personaMarket'
import PersonaMarketCard from '@/components/market/PersonaMarketCard'
import PersonaMarketDetailModal from '@/components/market/PersonaMarketDetailModal'

const { Title } = Typography

export default function MarketPage() {
  const [items, setItems] = useState<MarketCard[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState<string>('popular')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [detailId, setDetailId] = useState<string | null>(null)

  const fetchList = useCallback(() => {
    setLoading(true)
    personaMarketApi.listMarket({
      sort: sort as 'popular' | 'newest' | 'rating',
      search: search || undefined,
      page,
      page_size: 20,
    }).then((res) => {
      setItems(res.items)
      setTotal(res.total)
    }).finally(() => setLoading(false))
  }, [page, sort, search])

  useEffect(() => { fetchList() }, [fetchList])

  const handleImported = useCallback(() => { fetchList() }, [fetchList])

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px 16px' }}>
      <Title level={3}>🛒 角色市场</Title>

      <Space style={{ marginBottom: 16, width: '100%' }} direction="vertical">
        <Input.Search
          placeholder="搜索角色..."
          allowClear
          onSearch={(val) => { setSearch(val); setPage(1) }}
          prefix={<SearchOutlined />}
          style={{ maxWidth: 400 }}
        />
        <Segmented
          value={sort}
          onChange={(val) => { setSort(val as string); setPage(1) }}
          options={[
            { label: '🔥 热门', value: 'popular' },
            { label: '⭐ 评分', value: 'rating' },
            { label: '🆕 最新', value: 'newest' },
          ]}
        />
      </Space>

      {loading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} active paragraph={{ rows: 3 }} />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Empty description="暂无角色" />
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16, alignItems: 'stretch' }}>
            {items.map((item) => (
              <div key={item.id} onClick={() => setDetailId(item.id)} style={{ display: 'flex' }}>
                <PersonaMarketCard item={item} onImported={handleImported} />
              </div>
            ))}
          </div>
        </>
      )}

      <Pagination
        current={page}
        total={total}
        pageSize={20}
        onChange={setPage}
        style={{ textAlign: 'center', marginTop: 24 }}
        responsive
      />

      <PersonaMarketDetailModal
        listingId={detailId}
        open={detailId !== null}
        onClose={() => setDetailId(null)}
        onImported={handleImported}
      />
    </div>
  )
}
