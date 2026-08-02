## 1. 依赖与基础设施

- [ ] 1.1 `cd web && npm install react-virtuoso`
- [ ] 1.2 新建 `web/src/components/VirtualMessageList.tsx` — 共享虚拟列表包装组件，接受 `messages`、`renderItem`、`estimateSize`、`atBottomStateChange` props

## 2. 消息条目组件提取（React.memo）

- [ ] 2.1 GroupChatPage: 提取 `UserMessageItem` 组件（`React.memo`）— 当前内联渲染的真人消息逻辑（行 1194-1308）
- [ ] 2.2 GroupChatPage: 提取 `AIMessageItem` 组件（`React.memo`）— 当前内联渲染的 AI 消息逻辑，含 toolRuns chips（行 1340-1420）
- [ ] 2.3 GroupChatPage: 提取 `TaskPlanCard` 组件（`React.memo`）— 当前内联渲染的任务协作卡片（行 1328-1388）
- [ ] 2.4 为每个 `React.memo` 组件实现自定义 `arePropsEqual` 比较函数（仅比较 content/streaming/toolRuns.length/taskSteps status）
- [ ] 2.5 ChatPage: 同理提取消息条目组件，复用 `MessageItem.tsx` 已有的逻辑结构

## 3. GroupChatPage 接入虚拟列表

- [ ] 3.1 将 GroupChatPage 的 `messages.map(...)` 替换为 `<VirtualMessageList messages={...} renderItem={...} />`
- [ ] 3.2 配置 `followOutput="smooth"` + `atBottomThreshold={100}` 实现自动滚底
- [ ] 3.3 处理 `atBottomStateChange` 实现用户上滑暂停跟随、回底部恢复跟随
- [ ] 3.4 配置 `increaseViewportBy={{ top: 200, bottom: 200 }}` 减少 MarkdownMessage 重新挂载频率
- [ ] 3.5 移除手写滚动逻辑：删除 `useEffect(() => { scrollTop = scrollHeight }, [messages.length])` 块
- [ ] 3.6 移除手写的 `scrollRef`，改用 Virtuoso 内置的 `scrollerRef`

## 4. ChatPage 接入虚拟列表

- [ ] 4.1 将 ChatPage 的消息列表渲染替换为 `<VirtualMessageList>`，传入单聊的 `messages` 和 `renderItem`
- [ ] 4.2 配置自动滚底行为（与 GroupChatPage 一致）
- [ ] 4.3 移除手写滚动逻辑

## 5. 验证与收尾

- [ ] 5.1 确认流式输出时新 token 能触发高度正确更新（ResizeObserver 自动处理）
- [ ] 5.2 确认工具调用 chip 展开/折叠后布局正确
- [ ] 5.3 确认任务协作卡片中 subtask 状态变更时高度正确更新
- [ ] 5.4 确认 200+ 条消息时滚动性能（Chrome DevTools Performance 面板）
- [ ] 5.5 `cd web && npm run build` — TypeScript + Vite 构建通过
