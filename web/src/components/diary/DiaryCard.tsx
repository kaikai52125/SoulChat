import { useState } from 'react'
import { Card, Typography, Tag, Badge } from 'antd'
import type { DiaryEntry } from '@/api/personaDiary'

const { Text, Paragraph } = Typography

interface Props {
  diary: DiaryEntry
  personaName?: string
}

const MOOD_ICONS: Record<string, string> = {
  warm: '💛',
  playful: '😄',
  concerned: '💭',
  proud: '🌟',
  neutral: '📝',
  thoughtful: '🤔',
}

export default function DiaryCard({ diary, personaName }: Props) {
  const [expanded, setExpanded] = useState(false)

  return (
    <Badge dot={!diary.is_read} offset={[-6, 6]}>
      <Card
        size="small"
        hoverable
        style={{ marginBottom: 12 }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Text strong style={{ fontSize: 14 }}>
            {MOOD_ICONS[diary.mood || 'neutral'] || '📝'}{' '}
            {diary.title || `${diary.diary_date} 的日记`}
          </Text>
          {personaName && (
            <Tag color="blue" style={{ marginLeft: 'auto' }}>
              {personaName}
            </Tag>
          )}
        </div>

        <Paragraph
          type="secondary"
          style={{ margin: 0 }}
          ellipsis={!expanded ? { rows: 2 } : false}
        >
          {diary.content}
        </Paragraph>

        {diary.key_topics.length > 0 && (
          <div style={{ marginTop: 8 }}>
            {diary.key_topics.map((t) => (
              <Tag key={t} style={{ fontSize: 11 }}>{t}</Tag>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {diary.diary_date} · {diary.word_count} 字
          </Text>
          {!diary.is_read && <Badge status="processing" text="未读" />}
        </div>
      </Card>
    </Badge>
  )
}
