## Context

当前角色系统三种交互模式：

```
1v1 聊天:   用户 ↔ [角色A + 工具]                    角色间不可见
群聊:       用户 → Host → A→B→C 轮流发言              工具不可用
Research:   Pipeline（无角色交互）                     只用外部工具
```

Agent-as-Tool 填补第四种模式：

```
任务聊天:   用户 ↔ [角色A + 工具 + 角色B(作为工具)]
                         │
                         ├→ knowledge_search
                         ├→ memory_search
                         └→ call_agent("代码审查官", code="...")
```

**业界参考**：
- **A2A 协议** (Google, 2025.04)：Agent Card 描述能力，gRPC/HTTP 通信，150+ 组织采用
- **LangGraph Command API**：跨 parent/child subgraph 的 handoff 机制
- **CrewAI Agent-as-Tool**：角色包装为工具，供其他 Agent 调用

SoulChat 不需要引入完整的 A2A 协议栈（那是分布式多 Agent 场景的需求）。本地角色注册为工具是最轻量的实现。

**约束**：
- 被叫角色使用自己的 persona 配置（system_prompt + memory_text + temperature），独立推理
- 被叫角色**不**挂载工具（防止无限递归：A 调 B，B 又调 A）
- 调用是同步等待的（Agent-as-Tool 不是 fire-and-forget），和普通工具调用语义一致
- 只有标记了 `allow_agent_call=true` 的角色才能被其他角色调用

## Goals / Non-Goals

**Goals:**
- 角色包装为 `StructuredTool`，主叫角色可通过 tool_search 发现并调用
- 被叫角色使用自己的 persona 配置独立推理
- 调用结果以标准 ToolMessage 格式返回
- 调用过程透明可追踪（tracing span 标记为 agent_call）

**Non-Goals:**
- 不引入 A2A 协议（只做本地调用，不做跨网络角色发现）
- 被叫角色不挂载工具（防止递归调用）
- 不做角色间协商/辩论（那是群聊场景的扩展，不在此 proposal 范围）
- 不做被叫角色流式输出透传（返回最终结果，不返回中间过程）

## Decisions

### 决策 1：角色作为工具的实现方式

**选择**：每个 opt-in 的角色被包装为一个 `StructuredTool`，工具名为 `agent__{persona_name_slug}`，描述为该角色的 `system_prompt` 前 100 字摘要 + "该角色擅长..."。

```python
def build_agent_tool(persona) -> StructuredTool:
    async def _call_agent(query: str) -> str:
        model = build_chat_model(persona.temperature)
        messages = [
            SystemMessage(content=persona.system_prompt),
            HumanMessage(content=query)
        ]
        result = await model.ainvoke(messages)
        return result.content
    
    return StructuredTool.from_function(
        coroutine=_call_agent,
        name=f"agent__{slugify(persona.name)}",
        description=f"调用角色「{persona.name}」：{summarize(persona.system_prompt, 100)}",
        args_schema=CallAgentInput  # {query: str}
    )
```

**理由**：最简单的实现——被叫角色就是"给定专属 system_prompt，回答一个问题"——不需要工具、不需要历史、不需要 ReAct 循环。这是 Agent-as-Tool 的 MVP 形态。

### 决策 2：被叫角色不使用工具

**选择**：被叫角色调用 `model.ainvoke(messages)` 而非 `run_function_calling()`。挂载工具有两个风险：
1. **递归调用**：角色 A 调角色 B，B 又通过 tool_search 发现角色 A → 无限循环
2. **成本放大**：B 的 ReAct loop × 5 轮（最坏情况），嵌套在 A 的 loop 里 → 延迟和成本爆炸

**理由**：角色被当作工具调用时，它的职责是"提供专业判断/补充视角"，不是"执行复杂任务"（那是主叫角色的工作）。纯 LLM 推理 + persona 配置已经足够。未来如果发现需要工具的场景，可以加 `allow_agent_tool_access` 白名单，但初版严格禁止。

### 决策 3：角色工具的发现和注册

**选择**：角色工具进入 `dynamic-tool-discovery` 的扩展层。在 `build_enabled_tools()` 中：

```python
# 加载与当前活跃角色不同的 opt-in 角色作为工具
if persona.allow_agent_call:
    other_personas = await persona_repo.list_callable(user_id, exclude_id=persona.id)
    for p in other_personas:
        tool = build_agent_tool(p)
        tools.append(tool)
        TOOL_EMBEDDING_CACHE[tool.name] = await embed(tool.description)
```

**理由**：角色工具在工具发现系统中的处理方式与 MCP 工具完全一致——都在扩展层，都通过 tool_search 按需发现，都有 embedding 缓存。这最大程度复用 `dynamic-tool-discovery` 的基础设施。

### 决策 4：`allow_agent_call` 字段设计

**选择**：`agent_personas` 表新增 `allow_agent_call BOOLEAN DEFAULT FALSE`。前端在 PersonaEditModal 的 Tools 标签页展示开关 + 提示："开启后此角色可被其他角色作为工具调用"。

**理由**：默认关闭是安全设计——大多数角色不需要被其他角色调用（如"朋友的吐槽角色"）。只有专业角色（"代码审查官""翻译官""经济学家"）才有 opt-in 价值。

## Risks / Trade-offs

- **[被叫质量不稳定]** 被叫角色只有单轮 LLM 调用，没有 ReAct 循环和工具支持 → **缓解**：(1) 角色被调用时的任务通常是"审查/翻译/判断"，单轮推理足够；(2) system_prompt 的角色设定天然适合这类任务
- **[延迟叠加]** A 的 ReAct loop 中调用 B，B 做推理产生额外延迟 → **缓解**：(1) 被叫角色不做 ReAct，只做单轮推理；(2) 被叫角色和普通工具一样享受并行执行（Agent 可以同时调 B + knowledge_search）；(3) Agent 不会频繁调用其他角色（工具描述让主叫角色有意识判断是否必要）
- **[角色发现精准度]** tool_search 返回的角色可能与实际需求不匹配（如把"经济学家"返回给"写代码"的查询）→ **缓解**：tool_search embedding 基于角色 description（system_prompt 摘要），准确度取决于角色配置质量。后续可引入"角色标签"辅助匹配
