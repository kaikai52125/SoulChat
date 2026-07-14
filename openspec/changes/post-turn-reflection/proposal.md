## Why

当前聊天的 Agent 循环是"单行道"——LLM 输出答案后就结束，不评估自己的回答质量。而 Research 模式已经有一套成熟的 Verifier Loop 基础设施（Generate → Verify → Decide → Repair，跨模型验证，6 维评分 rubric）。两者的设计资产没有打通。

加入一个轻量的 post-turn 反思步骤：每次回答后追加一次极快的 self-check，检查"有没有遗漏关键信息？有没有该用但没用到的工具？"——结果追加写入 persona 的 `memory_text`，让角色随着使用次数增加而积累交互经验。

这不是 Research 模式的重量级 Verifier Loop 直接搬过来——聊天的反思更快（单次 LLM 调用，不需要循环迭代）、更轻（只做 3 维判断，不重写内容）、有副作用（写入角色记忆）。

## What Changes

- 新增 `ChatReflector` 模块（`core/agent/reflector.py`）——聊天专用的轻量反思器
- 聊天路径末尾：Agent 回答完成（`final` 事件已发送）后，异步（非阻塞）执行一次 self-check
- Self-check prompt 从 3 个维度检查：
  1. **完整性**：有没有遗漏用户问题中的关键信息？
  2. **工具利用**：有没有该用但没调用的工具？
  3. **用户满意度**：回答是否直接命中了用户意图？
- 反思结果格式化写入 persona 的 `memory_text`（append 模式），附时间戳和对话摘要
- `memory_text` 积累的反思按时间倒序排列，最新的 10 条注入 system prompt（替代全量注入）
- 反思写入是后台任务，不阻塞 answer 流式返回
- 配置文件开关：`chat_reflection_enabled`（默认开启），`chat_reflection_model`（可独立于聊天模型配置，默认复用）

## Capabilities

### New Capabilities

- `chat-reflection`: 聊天路径支持轻量 post-turn 自我反思，结果写入角色记忆
- `reflection-aware-system-prompt`: 角色 system prompt 可注入近期反思作为"经验上下文"

## Impact

- **新文件** (`core/agent/reflector.py`): ChatReflector 独立模块，约 100-150 行
- **聊天服务** (`services/chat_service.py`): `_run_chat_turn_bg()` 末尾追加 `_schedule_reflection()` 后台调用
- **角色记忆** (`models/agent_persona_model.py`): `memory_text` 新增反思块格式约定（不改变字段类型）
- **System prompt 组装** (`services/chat_service.py` `_compose_system_prompt()`): 从 `memory_text` 提取最近 10 条反思注入 prompt
- **设置** (`config.py`): 新增 `chat_reflection_enabled` 和 `chat_reflection_model` 配置项
- **前端** (`PersonaEditModal.tsx`): Memory 标签页可选展示反思分区，可选开关
