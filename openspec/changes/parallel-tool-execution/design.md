## Context

当前 orchestrator 的 `run_function_calling` 在处理 `gathered.tool_calls` 时逐条 `await tool.ainvoke(args)`：

```python
for tc in gathered.tool_calls:
    # ... 串行执行每个工具
    result = await tool.ainvoke(tc["args"])
```

当 LLM 决定同时调用多个独立工具时（如 knowledge_search + memory_search），延迟叠加。且调用缓存 `call_cache` 已经按 `(tool_name, args)` 去重，同一 turn 内不会重复执行，并行化不存在数据一致性问题。

**约束**：
- 不改变事件协议（`tool_start` / `tool_result` 仍然逐条发射，前端顺序不乱）
- 不改变调用缓存语义（同一 turn 内相同参数仍然复用）
- 不改 chat_service 或 group_chat_service 的调用方式
- 保持或降低错误处理不劣于当前（单个工具失败不影响其他工具）

## Goals / Non-Goals

**Goals:**
- function calling 路径：多工具并行执行 (`asyncio.gather`)，延迟 = max(t_i)
- ReAct 路径：支持解析多个 Action/Action Input 对，并行执行
- 并行结果全部收集后统一追加 ToolMessage 回 messages
- 单个工具异常不阻断并行组中其他工具的执行

**Non-Goals:**
- 不做工具依赖分析（无需 DAG 拓扑排序 —— 工具互不依赖，有依赖的 LLM 自然会分两轮调用）
- 不改 `run_function_calling` 的流式 token 发射逻辑
- 不改 MCP 工具加载/连接管理
- 不新增配置开关（并行是纯优化，无 trade-off，不需要开关）

## Decisions

### 决策 1：function calling 路径并行策略

**选择**：`results = await asyncio.gather(*[tool.ainvoke(args) for tc in tool_calls], return_exceptions=True)`

**理由**：`return_exceptions=True` 确保单个工具抛异常不取消其他工具的执行。每个结果单独检查 `isinstance(result, Exception)`，异常的 observation 仍为 `"工具执行失败：{e}"`，status 为 `"error"`。与当前串行版本的行为完全一致——错误被封装为 ToolMessage 而非传播。

`asyncio.gather` 对纯 I/O 操作（ES 查询、Neo4j 查询、HTTP 调用）是最精确的并行原语，无需引入 `ThreadPoolExecutor`。

### 决策 2：事件发射保持串行

**选择**：并行执行的结果收集后，仍用 `for` 循环逐条 `yield tool_start`、`yield tool_result`。

**理由**：前端按事件到达顺序渲染 tool chip，并行 yield 会导致 chip 出现顺序不确定。延迟优化在工具执行阶段（占 95%+ 时间），事件发射阶段（dict 构造 + yield）耗时可忽略不计。

### 决策 3：ReAct 路径多 Action 解析

**选择**：`_ACTION_RE` / `_ACTION_INPUT_RE` 改为 `re.finditer` 遍历所有匹配对，假设 Action 和 Action Input 按顺序配对。

**理由**：ReAct 是 prompt 范式，没有原生结构化输出保证。最简单、最兼容的解析方式仍是正则。多 Action 的语义是"上一轮 Thought 决定了这三个查询是独立的"——模型在 ReAct prompt 里可以输出：

```
Thought: 需要同时查三个来源
Action: memory_search
Action Input: 用户喜欢什么编程语言
Action: knowledge_search
Action Input: Python vs Go 性能对比
Action: web_search
Action Input: best programming language 2026
```

`finditer` 按出现顺序配对，短了忽略，多了截断。

### 决策 4：不引入工具依赖分析

**选择**：不做 DAG 拓扑排序，不分析工具间数据依赖。

**理由**：LLM 自己就是最好的依赖分析器——有依赖的工具调用（先用 A 的结果找 B），LLM 会自然地分两轮：第一轮调 A，第二轮看到 A 的结果再调 B。强行在 orchestrator 层分析工具依赖反而引入复杂度和出错风险。并行化只优化"LLM 已经决定可以同时调"的情况。

### 决策 5：不改 ReAct 路径的 tool args 格式

**选择**：ReAct 多 Action 仍用 `tool.ainvoke({"query": query})`（单参数 `query`）。

**理由**：ReAct 路径当前硬编码 `{"query": query}`，所有内置工具的 `query` 参数都是 `Field(alias="query")`，兼容此调用方式。保持此约束，此改动不扩展到结构化参数（那是另一个 proposal 的范围）。

## Risks / Trade-offs

- **[顺序依赖误判]** 极少数情况下，LLM 在一次迭代中输出了有依赖关系的工具调用（如 tool A 的结果应该作为 tool B 的输入），并行执行时 tool B 会在缺少 A 结果的情况下运行 → **缓解**：这种情况 LLM 本身就不应该把 B 放在同一轮（没有 A 的结果它写不出 B 的正确 args）。如果发生，结果仍然一致——B 和串行版本一样返回结果，只是没有利用 A 的信息（和串行版本一样差）。且调用缓存在下轮迭代中会复用本轮结果，不影响最终效果
- **[并发竞态]** 多个工具共享 `ctx.stats_holder` 写入 stats → **缓解**：每个工具写入自己的 key（如 `stats_holder["memory_search"] = {...}`），不同 key 不竞态。`ctx.citations` 同理，每个工具 `append` 自己的引用，asyncio 的 list.append 在 CPython 中是原子操作
