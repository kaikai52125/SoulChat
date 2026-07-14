## Why

当前群聊是"社交模拟"——Host LLM 选发言顺序，角色轮流说话，对话记录纯文本。这与"任务协作"是本质不同的场景：

| | 社交模拟（当前群聊） | 任务协作（本 proposal） |
|---|---|---|
| 目标 | 对话看起来自然有趣 | 产出高质量的答案/作品 |
| 交互 | 角色轮流发言 | Orchestrator 分解任务 → 并行委派 → 汇总 |
| 状态 | 纯文本对话记录 | 共享黑板（结构化产物 + 协商记录） |
| 质量保证 | 无 | Verifier 审查 + 迭代修订 |

本 proposal 引入 **Orchestrator-Worker** 模式替代当前的 Host-LLM-轮询模式，在群聊中新增"任务模式"——用户可以选择发起一个协作任务，Orchestrator 分解给角色组中的成员，通过共享黑板协作，最终汇总为一个完整产出。

业界数据支撑：SE-Blackboard (IEEE 2026) — 共享状态黑板比消息传递信息保真度 +62%；Mycelium (Cisco 2026) — 结构化协商 93% 决策收敛 vs 非结构化聊天 36%。

## Dependencies

- **依赖 `parallel-tool-execution`**: 角色的任务分配后并行执行
- **依赖 `dynamic-tool-discovery`**: Orchestrator 需要知道各角色的能力
- **依赖 `agent-as-tool`**: 群聊协作模式下，角色间调用也是 Agent-as-Tool 的一个应用场景
- **依赖 `two-speed-agent-router`**: 任务模式下 Planner 生成协作 DAG

## What Changes

- `group_chat.py` 新增 `TaskCollaborationMode` —— 群聊中用户发送"任务模式"指令或 API 参数切换
- **Orchestrator Agent**（替代当前 Host LLM 的简单轮询）：分解任务 → 生成角色-子任务映射 → 并行委派
- **Shared Blackboard**：角色间共享的结构化状态空间（任务定义、各角色输出、评论、最终汇总），是协作的核心数据层
- **Quality Verifier**：复用现有 Verifier Loop 基础设施，在协作模式下审查最终产出
- 当前"社交模式"群聊保留不变（Host LLM 选发言顺序），任务模式是新增入口
- 角色仍使用自己的 persona 配置独立推理（和 agent-as-tool 的模式一致）
- 前端群聊页可切换"社交模式 / 任务模式"

## Capabilities

### New Capabilities

- `task-collaboration-mode`: 群聊新增任务协作模式，Orchestrator-Worker 架构
- `shared-blackboard`: 角色间共享结构化状态空间，替代纯文本对话
- `collaborative-quality-verification`: 协作产出经过 Verifier Loop 审查

### Modified Capabilities

- `group-chat-orchestration`: `group_chat.py` 的双模式（社交 / 任务协作）

## Impact

- **群聊代理** (`core/agent/group_chat.py`): 最大改动，新增 `TaskCollaborationMode` 类 + `SharedBlackboard` 类
- **编排器** (`core/agent/orchestrator.py`): 不直接改动，被 TaskCollaborationMode 复用 `run_function_calling()`
- **提示词** (`prompts/`): 新增 `task_orchestrator.jinja2` + `blackboard_summarizer.jinja2`
- **群聊服务** (`services/group_chat_service.py`): 新增协作模式路由
- **前端** (`GroupChatPage.tsx`): 新增模式切换、黑板展示区
- **Verifier Loop** (`core/agent/loop/`): 新增协作产出 rubric（复用现有架构）
