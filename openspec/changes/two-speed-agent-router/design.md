## Context

当前 SoulChat 聊天的调度路径：

```
用户消息 → _generate_events()
              ├─ 无工具 → 裸 LLM 流式
              ├─ 强模型 + 工具 → run_function_calling()  [ReAct loop × 5]
              └─ 弱模型 + 工具 → run_react()             [ReAct loop × 5]
```

这个路径的问题是**所有消息一视同仁**——"你好"和"帮我写一份 Python vs Go 的性能对比报告，要从 CPU、内存、并发三个维度各找一份 benchmark 数据，最后用表格汇总"走完全相同的流程。

2025-2026 业界共识的 "Two-Speed Design"：

```
用户消息 → Cheap Router → 
  ├─ trivial     → 裸 LLM（不加载工具，不调记忆）
  ├─ chat        → LLM + 记忆（纯对话，不挂工具）
  ├─ single_tool → ReAct loop（当前行为，单工具查询）
  └─ multi_step  → Micro-Planner（生成 DAG）→ DAG Executor → 汇总
```

Research 模式已经有了 pipeline 设计。本 proposal 把这个设计模式降维到聊天场景。

**前提依赖**：
- `parallel-tool-execution`：DAG 同层节点并行执行依赖异步 gather
- `dynamic-tool-discovery`：Planner 需要知道当前可用工具有哪些（核心 + 可发现的扩展）

**约束**：
- Router 必须极快（轻量模型 + 极短 prompt，目标 < 500ms）
- 保留 `run_function_calling()` 和 `run_react()` 作为 fallback
- 不改现有事件协议（`token` / `tool_start` / `tool_result` / `final`）
- 对过去对话历史负载透明（前端/API 无变化）

## Goals / Non-Goals

**Goals:**
- Router 4 路分类：trivial / chat / single_tool / multi_step
- multi_step 路径：Micro-Planner 生成 ≤4 步 DAG → DAG Executor 执行 → 汇总
- DAG 同层节点并行执行（利用 parallel-tool-execution）
- Router 失败 → fallback 到 `run_function_calling()` （graceful degradation）
- single_tool 和 chat 路径延迟不劣于当前（Router 开销 < 500ms）

**Non-Goals:**
- 不做动态 replan（执行中重新规划）—— 初版 Planner 一次性规划，后续迭代加
- 不做跨 turn 的 plan 持久化
- 不做用户可见的 plan 展示（前端不显示 DAG 图）
- 不替换 Research 模式的 pipeline（两者独立演进）

## Decisions

### 决策 1：Router 设计 —— 4 路分类

**选择**：Router 用轻量模型（`gpt-4o-mini` 或用户配置的 router_model），prompt 极短（~200 token），输出严格 JSON：

```json
{
  "route": "trivial|chat|single_tool|multi_step",
  "confidence": 0.95,
  "reason": "一句话理由"
}
```

**分类逻辑**：
- `trivial`：纯闲聊/问候（"你好""谢谢""今天天气不错"），不需要任何工具和记忆检索
- `chat`：对话性但有实质内容（"你觉得 Python 怎么样""给我解释一下什么是闭包"），需要记忆上下文但不需要工具
- `single_tool`：需要 1 个工具（"帮我查知识库里关于 Python 的文档""搜索最近的 AI 新闻"）
- `multi_step`：需要多步推理/多工具/多轮（"比较 A 和 B，各找 3 个例子，用表格输出"）

**Router 非 LLM 实现**：在实际部署中，可以用规则 + embedding 相似度组合替代 LLM Router：
- 规则：消息长度 < 10 字 → trivial 候选；"帮我" + 动词 → multi_step 候选
- Embedding：计算消息与各路由类别典型样本的余弦相似度
- LLM Router 作为 "不确定时" 的仲裁器（confidence < 阈值时触发）

初版先上 LLM Router（实现简单，准确率高），后续优化为规则 + embedding 混合路由。

### 决策 2：Micro-Planner —— ≤4 步 DAG

**选择**：Planner 根据用户消息 + 可用工具列表生成一个小 DAG（节点 ≤ 4，深度 ≤ 2）：

```json
{
  "goal": "一句话目标描述",
  "steps": [
    {
      "id": "step_1",
      "description": "搜索 Python 性能 benchmark",
      "tool_hint": "web_search",
      "query_hint": "Python performance benchmark 2026",
      "dependencies": [],
      "expected_output": "benchmark 数据列表"
    },
    {
      "id": "step_2", 
      "description": "搜索 Go 性能 benchmark",
      "tool_hint": "web_search",
      "query_hint": "Go performance benchmark 2026",
      "dependencies": [],
      "expected_output": "benchmark 数据列表"
    },
    {
      "id": "step_3",
      "description": "从知识库获取 Python vs Go 对比资料",
      "tool_hint": "knowledge_search",
      "query_hint": "Python Go 性能对比",
      "dependencies": [],
      "expected_output": "文档摘要"
    },
    {
      "id": "step_4",
      "description": "综合前三步结果，生成 CPU/内存/并发三维度对比表格",
      "tool_hint": null,
      "query_hint": null,
      "dependencies": ["step_1", "step_2", "step_3"],
      "expected_output": "Markdown 格式对比表格"
    }
  ]
}
```

**关键约束**：
- 最多 4 步（防止 planner 过度分解导致总延迟失控）
- 深度最多 2 层（保证至少一层并行）
- `tool_hint` 是指示性的（实际执行时每步内仍走 ReAct，可以动态调整工具选择）
- `dependencies` 为空表示此步可以与其他空依赖步并行执行
- Step 4 无 `tool_hint` → 标记为"纯 LLM 综合步"，不加工具，直接让 LLM 基于前三步结果生成

### 决策 3：DAG Executor —— 拓扑排序 + 层内并行

**选择**：Executor 执行算法：

```python
async def execute_dag(steps, context) -> dict[str, str]:
    results = {}
    # 拓扑分层：依赖数为 0 的步在同一层
    while remaining_steps:
        ready = [s for s in remaining_steps if all(d in results for d in s.dependencies)]
        
        # 层内并行执行
        coros = [_execute_one_step(s, context, results) for s in ready]
        step_results = await asyncio.gather(*coros, return_exceptions=True)
        
        for step, result in zip(ready, step_results):
            results[step.id] = result if not isinstance(result, Exception) else f"执行失败: {result}"
    
    return results

async def _execute_one_step(step, context, prior_results):
    """单步执行：有 tool_hint → ReAct loop × 3; 无 tool_hint → 纯 LLM 综合"""
    if step.tool_hint:
        # 注入 prior_results 作为上下文
        return await run_function_calling(model, tools, messages, max_iter=3)
    else:
        # 综合步：LLM 直接生成，不调工具
        return await model.ainvoke(synthesize_prompt(step, prior_results))
```

**理由**：
- 拓扑分层是最简单的 DAG 调度算法，≤4 步的 DAG 不会出现复杂拓扑
- 层内 `asyncio.gather` 复用 `parallel-tool-execution` 的并行能力
- 每个有 `tool_hint` 的步骤内是**独立的 ReAct loop**（max 3 轮而非 5 轮，因为 Planner 已经做了高层规划，步骤内不需要深度探索）
- `tool_hint` 注入步骤描述作为初始 system prompt，而非强制工具选择（保留弹性）
- 综合步（无 `tool_hint`）不挂工具，让 LLM 专注做结果整合

### 决策 4：路由分发 + Fallback

**选择**：`run_two_speed()` 函数签名：

```python
async def run_two_speed(
    model, tools, messages, persona, router_model
) -> AsyncGenerator[dict, None]:
    # 1. Router 分类
    route = await classify_message(router_model, messages[-1].content, tools)
    
    # 2. 按路由分发
    if route == "trivial":
        async for event in stream_plain(model, messages):
            yield event
    elif route == "chat":
        async for event in stream_plain(model, messages):  # 不挂工具
            yield event
    elif route == "single_tool":
        async for event in run_function_calling(model, tools, messages):
            yield event
    else:  # multi_step
        try:
            plan = await generate_plan(model, messages[-1].content, tools)
            results = await execute_dag(plan.steps, ...)
            yield from synthesize_results(model, plan, results)
        except PlanError:
            # fallback 到标准 FC 路径
            async for event in run_function_calling(model, tools, messages):
                yield event
```

**理由**：Router 或 Planner 失败时 graceful degradation 回 `run_function_calling()`，确保可用性不降级。`trivial` 和 `chat` 路径不加载工具——节省 prompt token 和工具构建时间。

### 决策 5：DAG 执行中事件透传

**选择**：DAG 的并行步骤产生的事件需要加上步骤标识（`step_id`），前端按步骤分组展示。

扩展事件协议（向后兼容）：
```python
{"type": "tool_start", "tool": "...", "query": "...", "step_id": "step_1"}  # 新增 step_id
{"type": "step_start", "step_id": "step_1", "description": "搜索 Python benchmark"}
{"type": "step_done", "step_id": "step_1", "status": "ok"}
```

**理由**：前端现有 tool_start/tool_result chip 渲染保持不变（`step_id` 是可选字段）。未来前端可显示"正在执行第 1/3 步：搜索 Python benchmark"的步骤进度条，但不阻塞当前发布。

## Risks / Trade-offs

- **[Router 误判]** Router 把 multi_step 判为 single_tool → 回答不完整 → **缓解**：(1) Fallback 到 FC 路径兜底，Agent 仍能回答只是没享受 planner 优化；(2) Router confidence < 阈值时 conservatively 判为 multi_step；(3) 后续数据积累后可微调 Router
- **[Planner 质量]** Planner 生成的 DAG 可能不够优（工具选择错误、步骤粒度不合理）→ **缓解**：(1) ≤4 步限制防止过度分解；(2) `tool_hint` 是指示性而非强制性（每步内 ReAct 可动态调整）；(3) DAG 深度 ≤2 确保总有并行机会
- **[延迟增加]** trivial/single_tool 路径会增加 Router 的一轮 LLM 调用（~500ms）→ **缓解**：(1) Router 用最轻模型（如 gpt-4o-mini），控制在 ~300ms；(2) multi_step 路径下 Planner 调用被并行执行节省的时间抵消（甚至净加速）；(3) 后续混合 Router 可降至 ~50ms
- **[与 Research 模式重叠]** Planner 和 Research 的 `make_plan` 功能有交集→ **接受**：两者适用场景不同（聊天 DAG 最多 4 步、Research Plan 是章节大纲），代码层面独立实现
