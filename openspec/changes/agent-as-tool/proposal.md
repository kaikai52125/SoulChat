## Why

当前角色之间的交互仅限于群聊模式（Host LLM 决定发言人 → 角色轮流说话），或完全不交互（一对一聊天模式角色互相不可见）。缺少一个关键模式：角色 A 在进行任务时，可以**把角色 B 当作工具来调用**——就像调用 knowledge_search 一样——"让代码审查官帮我看看这段代码""让翻译官把这段日语翻成中文""让经济学家审一下这个结论"。

这个模式把"角色"从纯对话参与者升级为可被其他角色调用的**能力单元**。它和 MCP（垂直工具）及 A2A（Agent-to-Agent 通信协议）形成互补：MCP 连接外部服务，Agent-as-Tool 连接内部角色能力。

## Dependencies

- **依赖 `dynamic-tool-discovery`**: 其他角色需要出现在工具发现池中
- **依赖 `two-speed-agent-router`**: Router/Planner 需要能判断"这个任务适合委托给另一个角色"

## What Changes

- 新增 `AgentAsTool` 工具构造器（`tools/builtin/agent_tool.py`）——将一个角色包装为 `StructuredTool`
- `build_enabled_tools()` 新增"角色工具"层：从用户的其他非活跃角色中注册为可调用工具，注入 tool_search 的发现池
- 角色被调用时，使用该角色自己的 system_prompt + memory_text 作为系统提示，独立推理
- 调用结果以 ToolMessage 形式返回给主叫角色（和普通工具调用一样融入对话）
- 调用是同步的（async await），主叫角色等待被叫角色完成推理后才继续
- 角色需在 persona 配置中标记 `allow_agent_call: bool = False`（默认关闭，显式 opt-in）
- 群聊模式暂不接入（群聊是社交场景，不需要 agent-as-tool）

## Capabilities

### New Capabilities

- `agent-tool`: 角色包装为工具，允许角色间互相调用
- `agent-tool-discovery`: 其他角色出现在 tool_search 结果中，usage hint 为"该角色擅长..."

## Impact

- **新文件** (`tools/builtin/agent_tool.py`): AgentAsTool 构造器，~80 行
- **工具注册表** (`tools/registry.py`): `build_enabled_tools()` 新增角色工具层
- **角色模型** (`models/agent_persona_model.py`): 新增 `allow_agent_call` 字段
- **角色 Schema** (`schemas/agent_persona_schema.py`): 新增 `allow_agent_call` 字段
- **前端** (`PersonaEditModal.tsx`): Tools 标签页新增角色工具展示 + `allow_agent_call` 开关
