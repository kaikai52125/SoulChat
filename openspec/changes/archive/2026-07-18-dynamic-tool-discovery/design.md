## Context

当前 `build_enabled_tools()` 返回所有启用工具的 `StructuredTool` 列表，全部 `model.bind_tools(tools)` 注入 prompt。工具数量 = 6(内置) + MCP Server 工具 + Skill 工具。用户挂载 MCP Server 越多，工具列表越长。

**业界数据参考**：
- MCPToolBench++：单个工具 schema 描述 288-657 token
- BFCL v3：工具数超过 20 时，多轮轨迹准确率从 85-90% 降至 55-65%
- Anthropic Tool Search Tool：动态返回 3-5 个最相关工具，节省数千 token

**面临的权衡**：完全动态发现带来一个额外 LLM 调用（tool_search 本身就是一次 tool call），对于单工具任务反而增加延迟。所以需要**分层策略**——核心工具始终可用，扩展工具按需发现。

**约束**：
- 不改变现有工具接口（`StructuredTool` / `ToolSpec` 不变）
- 不要求 MCP Server 重连做工具发现（利用缓存）
- `tool_search` 本身是普通工具，Agent 自行决定何时调用
- 用户可配置哪些工具是"核心"（始终注入）vs"扩展"（按需发现）

## Goals / Non-Goals

**Goals:**
- 核心工具（knowledge, memory, web, datetime）始终直接注入 system prompt
- MCP/Skill 扩展工具通过 `tool_search` 工具按需发现
- 工具 embedding 预计算并缓存（避免每次 tool_search 都调 embedding API）
- Agent 在一次 ReAct 循环中可以先调 tool_search 发现工具，然后在同一轮调实际工具（利用调用缓存）

**Non-Goals:**
- 不做自动工具依赖推理（不分析"用 A 的结果作为 B 的参数"）
- 不改变现有 MCP connection 管理
- 不新增用户可见的工具管理 UI（先只做能力，配置用 DB/API）
- 不引入外部向量数据库（利用现有 ES 或内存计算 embedding 余弦相似度）

## Decisions

### 决策 1：分层策略 —— 核心直接注入 + 扩展按需发现

**选择**：内置工具和 skill_executor 工具分成"核心"和"扩展"两层。

```
核心层（始终注入 schema）:
  - knowledge_search, memory_search, web_search, datetime
  - create_scheduled_task, save_to_persona_memory
  - 标记为 default_enabled=True 且 tool_keys 为空（无限制）的内置工具

扩展层（按 tool_search 发现）:
  - 所有 MCP 工具（如 weather__get_forecast, database__query_table）
  - Skill 脚本工具（如 skill__analyze_csv）
```

**理由**：核心工具仅 6 个，占 ~2000 token，不会引起工具臃肿。同时这些是对话中 90%+ 的工具调用场景，直接可用避免额外的 tool_search 调用。

用户可以通过 persona 的 `tool_keys` 字段（JSONB）显式指定：`{"core": ["knowledge_search", "memory_search"], "extended": ["mcp_server_1__get_data"]}` 覆盖默认分层。

### 决策 2：tool_search 本身是普通内置工具

**选择**：`tool_search` 注册为 `ToolSpec(key="tool_search", name="工具查找", ...)`，和其他工具一样进入 `BUILTIN_REGISTRY`。Agent 在 ReAct 循环中调用它。

**输入**：
```python
class ToolSearchInput(BaseModel):
    intent: str = Field(description="你想完成什么操作？用自然语言描述意图")
    top_k: int = Field(default=5, ge=1, le=10)
```

**输出**：
```python
"找到 3 个相关工具：\n"
"1. weather__get_forecast —— 获取指定城市的天气预报，参数: city(str, 必填), days(int, 可选)\n"
"2. database__query_table —— 执行 SQL 查询，参数: sql(str, 必填)\n"
"..."
```

**理由**：作为普通工具而非"系统级钩子"的好处——(1) 不修改 orchestrator 循环逻辑；(2) Agent 自己判断是否需要（简单问题时根本不会调）；(3) tool_search 的调用结果也享受调用缓存（同一 turn 内重复调用相同 intent 直接命中缓存）。

### 决策 3：工具 embedding 匹配用内存余弦相似度

**选择**：注册表维护 `_TOOL_EMBEDDING_CACHE: dict[str, list[float]] = {}`（key → embedding），MCP 工具加载时预计算 embedding。tool_search 调用时做内存余弦相似度 + Top-K。

**理由**：核心工具 6 个 + MCP 工具 50 个左右的规模，暴力余弦计算在内存中 < 5ms（嵌入维度 1536，50 个向量做余弦），不需要引入 ES 索引。embedding 预计算一次、进程级缓存，tool_search 零外部调用延迟。

### 决策 4：工具描述 embedding 内容 = key + name + description

**选择**：`embedding = embed(f"{tool_key}: {tool_name} —— {tool_description}")`

**理由**：key 是唯一标识，name 是中文名称，description 是功能描述。三者拼接覆盖了"Agent 会用什么语言描述需求"的各种可能。不做参数 schema 的 embedding 因为 schema 结构信息不适合向量相似度匹配（更适合结构化搜索，后续 Phase 考虑）。

### 决策 5：tool_search 对 ReAct 路径的适配

**选择**：ReAct 路径按同样方式享有 tool_search。tool_search 作为普通工具注入 ReAct 系统 prompt。

**理由**：ReAct prompt 中 tool_search 作为第一条工具列出，Agent 按 Thought → Action: tool_search → Action Input: "查询天气" 的正常流程使用。和 function calling 路径行为一致。

## Risks / Trade-offs

- **[额外 LLM 调用]** tool_search 本身是一次 tool call，对于需要多工具的复杂任务，第一轮会先调 tool_search 然后第二轮才调实际工具 → **缓解**：(1) 简单任务仍然直接调核心工具，不走 tool_search；(2) tool_search 返回极快（纯内存余弦计算 < 5ms）不增加实际延迟；(3) 节省的 prompt token 在 5+ 个 MCP Server 场景下远超额外调用的成本
- **[tool_search 未被调用]** Agent 可能忘记或选择不调 tool_search，直接用核心工具回答问题 → **缓解**：这是合理行为——说明核心工具已经满足需求。在 system prompt 中添加提示即可（"如果需要核心工具之外的额外能力（如操作数据库、发邮件），请先使用 tool_search 查找可用工具"）
- **[embedding 缓存过期]** MCP Server 工具列表变更后，缓存的 embedding 过期 → **缓解**：MCP tools_cache 已有 fingerprint 机制（60s TTL），embedding 跟随 tools_cache 一起刷新
