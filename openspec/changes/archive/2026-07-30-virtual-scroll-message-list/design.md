## Context

当前 ChatPage 和 GroupChatPage 的消息列表通过 `messages.map(m => <div key={m.id}>...</div>)` 内联渲染。每个 `MarkdownMessage` 实例独立 parse markdown，加上 `PersonaAvatar`、`AuthenticatedImage`、tool chip 等子组件，单条消息可产生 20-50 个 DOM 节点。200 条消息 = 4000-10000 个 DOM 节点，每次 `setMessages` 触发整个列表的 React reconciliation。

## Goals / Non-Goals

**Goals:**
- DOM 节点数从 O(n) 降到 O(可视消息数)，200 条消息时只渲染 ~15 条
- 流式输出（onToken 追加文本）时自动增长列表项高度
- 工具调用 chip 展开/折叠时自动调整高度
- 新消息自动滚底，用户手动上滑时暂停跟随
- 行为无感知——用户不应察觉到列表渲染方式变了

**Non-Goals:**
- 不改造 MarkdownMessage 内部的 markdown 解析性能（那是另一个问题）
- 不改造图片加载（已有 AuthenticatedImage）
- 不改动 ChatPage 和 GroupChatPage 的非消息列表部分（输入框、工具栏、侧栏）

## Decisions

### 1. 选型：react-virtuoso 而非 react-window

| 维度 | react-window | react-virtuoso |
|---|---|---|
| 动态高度 | 需手动测量 + 回传 `itemSize` | 内置 `ResizeObserver`，自动处理 |
| 反向列表（聊天气泡） | 需额外计算 offset | 内置 `followOutput` + `initialTopMostItemIndex` |
| 滚动到指定项 | `scrollToItem` | `scrollToIndex` |
| 流式追加内容 | 需手动调 `onItemsRendered` | 内置 `followOutput="smooth"` |
| 包体积 | ~6KB | ~15KB |

选 react-virtuoso：消息高度不可预测（流式文本、工具 chips、任务卡片），Virtuoso 的自动高度测量避免了复杂的手动 ResizeObserver 逻辑。

### 2. 组件提取策略

**内联渲染** → **独立 React.memo 组件**：

```
ChatPage / GroupChatPage
  └─ VirtualMessageList (共享新组件)
       └─ Virtuoso
            ├─ UserMessageItem (React.memo)
            ├─ AIMessageItem (React.memo)
            └─ TaskPlanCard (React.memo)
```

`React.memo` 的自定义比较函数只检查关键字段：

```typescript
// 仅当以下字段变化才重新渲染
arePropsEqual(prev, next) {
  return prev.content === next.content
    && prev.streaming === next.streaming
    && prev.toolRuns?.length === next.toolRuns?.length
    && prev.taskSteps?.every((s, i) => s.status === next.taskSteps?.[i]?.status)
}
```

### 3. 流式内容高度更新

Virtuoso 默认假设列表项高度不变。流式输出时 `content` 每 16ms 更新一次（token 节流后），需要通知 Virtuoso 重新测量。

方案：在 `useEffect` 中监听 `content` 变化，调用 Virtuoso 的 `react-virtuoso` 不直接暴露 `remeasure` API。改用 **key prop 技巧**：不在消息上改 key，依赖 Virtuoso 的 `ResizeObserver` 自动检测高度变化。`ResizeObserver` 是浏览器原生 API，当文本内容增长导致 DOM 高度变化时自动触发。

确认：`react-virtuoso` 内部使用 `ResizeObserver` 监听每个列表项。当 token 追加导致 `<div>` 变高时，Virtuoso 自动重新计算布局。**不需要额外代码。**

### 4. 自动滚底行为

```typescript
// Virtuoso 配置
<Virtuoso
  followOutput="smooth"           // 新内容自动滚到底
  atBottomThreshold={100}         // 距底部 100px 以内视为"在底部"
  atBottomStateChange={(atBottom) => {
    setUserScrolledUp(!atBottom)  // 用户上滑时记录
  }}
/>
```

逻辑：
- 用户滑到顶部看历史 → `atBottom = false` → 记录 `userScrolledUp = true`
- 用户滑回底部 → `atBottom = true` → `userScrolledUp = false` → 恢复自动跟随
- 新消息到达时：如果 `userScrolledUp = false`（在底部），自动跟随；否则不滚动

### 5. Shared 组件复用

两个页面目前各自内联渲染消息。提取后在 `web/src/components/VirtualMessageList.tsx` 创建一个共享包装组件：

```typescript
interface VirtualMessageListProps<T> {
  messages: T[]
  renderItem: (message: T) => React.ReactNode
  estimateSize?: number            // 预估高度，默认 120px
  atBottomStateChange?: (atBottom: boolean) => void
}
```

ChatPage 和 GroupChatPage 只需传入 `messages` + `renderItem`，不再各自管理滚动逻辑。

## Risks / Trade-offs

- **[风险] ResizeObserver 未触发高度更新**：某些情况下（如 display:none 切换），ResizeObserver 可能漏报。
  → 降级方案：手动 `requestAnimationFrame` 轮询特定消息的高度变化，超时后默认清理

- **[风险] 快速滚动时 MarkdownMessage 闪烁**：列表项离开可视区被卸载，回到可视区重新挂载，重新 parse markdown。react-virtuoso 默认卸载不可见项。
  → 配置 `increaseViewportBy={{ top: 200, bottom: 200 }}` 增加缓冲区和保留区，减少卸载频率

- **[风险] 搜索/跳转到历史消息**：用户想跳转到某条特定消息，虚拟列表需要 `scrollToIndex`，但当前没有索引查找能力。
  → 非目标：此功能当前不存在，不再本次范围。后续可用 `scrollToIndex(knownIndex)` 或先 `data.findIndex` 定位

- **[取舍] react-virtuoso vs react-window**：前者体积更大但配置更少。聊天场景的消息高度多变，减少手动测量的复杂度值得额外的 9KB。
