## 1. 数据模型

- [ ] 1.1 `models/agent_persona_model.py`：`AgentPersona` 新增 `allow_agent_call: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))`
- [ ] 1.2 `schemas/agent_persona_schema.py`：`PersonaCreate` / `PersonaUpdate` / `PersonaOut` 新增 `allow_agent_call: bool = False`
- [ ] 1.3 `migrations/`：生成 alembic migration（`uv run alembic revision --autogenerate -m "add allow_agent_call to agent_personas"`）

## 2. Agent-as-Tool 构造器

- [ ] 2.1 新建 `tools/builtin/agent_tool.py`：`build_agent_tool(persona)` 函数——包装角色为 `StructuredTool`
- [ ] 2.2 工具名格式 `agent__{slug}` —— 与 MCP 工具的 `server__tool` 格式一致（都用 `__` 分隔前缀）
- [ ] 2.3 工具描述 = persona.name + 100 字 system_prompt 摘要
- [ ] 2.4 输入 schema `CallAgentInput(BaseModel): query: str = Field(description="要问这个角色的问题")`
- [ ] 2.5 执行逻辑：`model.ainvoke([SystemMessage(persona.system_prompt), HumanMessage(query)])` —— 单轮推理，不挂工具
- [ ] 2.6 角色 memory_text 如果非空，注入 system prompt

## 3. 注册表集成

- [ ] 3.1 `tools/registry.py`：`build_enabled_tools()` 新增 `agent_tools` 参数或自动检测其他可调用角色
- [ ] 3.2 按 `allow_agent_call=true` 过滤，排除当前活跃角色自身
- [ ] 3.3 角色工具注册到 `_TOOL_EMBEDDING_CACHE`（复用 dynamic-tool-discovery 的缓存机制）
- [ ] 3.4 角色工具属于扩展层（`layer="extended"`），通过 tool_search 按需发现

## 4. Tracing

- [ ] 4.1 角色调用 wrapping 的 span 标记为 `"agent_call"`（区别于 `"tool_call"` 和 `"mcp_call"`）
- [ ] 4.2 span attributes 包含 `caller_persona_id` 和 `callee_persona_id`

## 5. 前端

- [ ] 5.1 `PersonaEditModal.tsx` Tools 标签页：`allow_agent_call` 开关 + 提示文案
- [ ] 5.2 人物角色卡片：可调用角色展示特殊标识（如徽章"可被调用"）

## 6. Persona Repository

- [ ] 6.1 `repositories/agent_persona_repository.py`：新增 `list_callable(user_id, exclude_id)` 查询方法

## 7. 测试计划

### 7.1 单元测试 (`api/tests/test_agent_tool.py`)

- [ ] 7.1.1 `test_build_agent_tool_name_format`: 角色 "代码审查官" → 工具名 `agent__dai_ma_shen_cha_guan`（slug 化，`__` 分隔前缀）
- [ ] 7.1.2 `test_build_agent_tool_description`: 工具描述包含 persona.name + system_prompt 前 100 字摘要
- [ ] 7.1.3 `test_agent_tool_invoke_uses_persona_config`: 调用时使用的 system prompt = persona.system_prompt，temperature = persona.temperature
- [ ] 7.1.4 `test_agent_tool_memory_text_injected`: persona.memory_text 非空时，注入 system prompt
- [ ] 7.1.5 `test_agent_tool_no_tools_mounted`: 被叫角色不挂载工具（验证 `model.ainvoke(messages)` 而非 `run_function_calling()`）
- [ ] 7.1.6 `test_agent_tool_single_turn_only`: 被叫角色只有单轮 `model.ainvoke`，不进入 ReAct 循环
- [ ] 7.1.7 `test_allow_agent_call_default_false`: 新创建 persona 的 `allow_agent_call` 默认为 false
- [ ] 7.1.8 `test_list_callable_excludes_self_and_not_allowed`: `list_callable()` 只返回 `allow_agent_call=true` 且 `id != exclude_id` 的角色
- [ ] 7.1.9 `test_call_agent_input_schema`: `CallAgentInput` 只有 `query: str` 一个必填字段

### 7.2 集成测试

- [ ] 7.2.1 `test_agent_tool_in_tool_search`: 角色 B opt-in 后，tool_search("审查代码") → Top-3 包含 `agent__{B_slug}`
- [ ] 7.2.2 `test_agent_tool_not_in_tool_search_when_disabled`: 角色 B 未 opt-in → tool_search("审查代码") → 不包含该角色工具
- [ ] 7.2.3 `test_e2e_agent_call_flow`: 角色 A 活跃 → 查询"帮我审查这段代码：def foo(): pass" → tool_search 发现角色 B（代码审查官）→ A 调 B → B 返回审查意见 → A 综合回答
- [ ] 7.2.4 `test_agent_call_span_type`: agent_call 的 tracing span 类型为 `"agent_call"`，attributes 含 caller/callee persona_id
- [ ] 7.2.5 `test_callee_response_not_in_history`: B 的回应不写入 conversation history（仅作为 ToolMessage 存在于当前 turn）

### 7.3 安全测试

- [ ] 7.3.1 `test_no_recursive_agent_call`: 角色 B 被调用时不载入工具，确认 B 无法再调 C（Mock `build_enabled_tools` → `assert_not_called`）
- [ ] 7.3.2 `test_agent_tool_not_in_core_layer`: 角色工具属于扩展层，不被 `build_enabled_tools(layered=True)` 直接注入 prompt
- [ ] 7.3.3 `test_self_not_callable`: 活跃角色 A 不能调用自己（`list_callable` 排除 exclude_id）

### 7.4 回归测试

- [ ] 7.4.1 `test_existing_persona_unchanged`: 现有 persona 的 `allow_agent_call` migration 后为 false，行为不变
- [ ] 7.4.2 `test_mcp_tools_unaffected`: agent_tool 的注册不影响现有 MCP 工具的正常加载和使用

### 7.5 Lint

- [ ] 7.5.1 `uv run ruff check .` 无新增 lint 问题
