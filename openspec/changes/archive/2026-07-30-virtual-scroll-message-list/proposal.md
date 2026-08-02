## Why

ChatPage 和 GroupChatPage 将消息列表全量渲染为 DOM 节点。群聊积累 200+ 条消息后，每条新 token 触发整个列表的 `.map()` 遍历和 React reconciliation，页面明显卡顿。引入虚拟滚动只渲染可视区域内的消息，将 DOM 节点数从 O(n) 降到 O(1)。

## What Changes

- **引入 react-virtuoso** 替代手写的 `.map()` 消息列表渲染
- **提取消息条目组件**：将 ChatPage 和 GroupChatPage 中的内联消息渲染提取为 `React.memo` 包裹的独立组件（`MessageBubble`、`TaskPlanCard`），供虚拟列表高效复用
- **处理动态高度**：流式 token 追加、工具调用展开/折叠、任务卡片状态变更都会改变列表项高度，需要通知 Virtuoso 重新测量
- **保持自动滚底行为**：新消息到达或流式内容更新时自动跟随滚动到底部，用户手动上滑查看历史时暂停跟随，一屏内回到底部时恢复跟随
- **移除手写滚动逻辑**：当前 `useEffect` + `scrollTop = scrollHeight` 的手动滚动替换为 Virtuoso 内置的 `followOutput`

## Capabilities

### New Capabilities

- `virtual-message-list`: 消息列表虚拟滚动能力，仅渲染可视区域内的消息条目，支持动态高度和自动滚底跟随

### Modified Capabilities

<!-- 无现有 spec 需要修改 -->

## Impact

- 新增依赖：`react-virtuoso` (~50KB gzipped)
- 影响文件：
  - `web/src/pages/ChatPage.tsx` — 消息列表渲染重构
  - `web/src/pages/GroupChatPage.tsx` — 消息列表渲染重构
  - `web/src/pages/chat/MessageItem.tsx` — 提取为虚拟列表条目组件
  - 新增 `web/src/components/VirtualMessageList.tsx` — 共享虚拟列表包装组件
- 行为不变：消息展示、工具调用、流式输出用户体验不受影响
