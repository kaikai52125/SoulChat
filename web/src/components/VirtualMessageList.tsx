/** 虚拟滚动消息列表 —— ChatPage 和 GroupChatPage 共用。 */
import { useCallback, useEffect, useRef } from 'react'
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso'

export interface VirtualMessageListProps {
  itemCount: number
  itemContent: (index: number) => React.ReactNode
  atBottomStateChange?: (atBottom: boolean) => void
  scrollToBottomRef?: React.MutableRefObject<(() => void) | null>
}

export default function VirtualMessageList({
  itemCount,
  itemContent,
  atBottomStateChange,
  scrollToBottomRef,
}: VirtualMessageListProps) {
  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const atBottomRef = useRef(true)
  const prevCountRef = useRef(itemCount)

  const handleAtBottomStateChange = useCallback(
    (atBottom: boolean) => {
      atBottomRef.current = atBottom
      atBottomStateChange?.(atBottom)
    },
    [atBottomStateChange],
  )

  // 新消息到达时：用户在底部 → 自动滚到底部；用户翻历史 → 不动
  useEffect(() => {
    if (itemCount > prevCountRef.current && atBottomRef.current) {
      virtuosoRef.current?.scrollToIndex({ index: itemCount - 1, behavior: 'smooth' })
    }
    prevCountRef.current = itemCount
  }, [itemCount])

  // 暴露滚动方法给外部（比如"回到底部"按钮）
  if (scrollToBottomRef) {
    scrollToBottomRef.current = () => {
      atBottomRef.current = true
      virtuosoRef.current?.scrollToIndex({ index: itemCount - 1, behavior: 'smooth' })
    }
  }

  return (
    <Virtuoso
      ref={virtuosoRef}
      totalCount={itemCount}
      itemContent={itemContent}
      initialTopMostItemIndex={itemCount > 0 ? itemCount - 1 : 0}
      initialItemCount={Math.min(itemCount, 20)}
      overscan={{ main: 400, reverse: 1200 }}
      atBottomThreshold={120}
      atBottomStateChange={handleAtBottomStateChange}
      increaseViewportBy={{ top: 80, bottom: 200 }}
      style={{ height: '100%' }}
    />
  )
}
