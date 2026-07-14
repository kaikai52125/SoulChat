## Context

Research 模式有一套完整的 Verifier Loop（Generate → Verify → Decide → Repair），但聊天 Agent 完全不走质量检查。根本原因不是"聊天不需要质量"，而是聊天的延迟敏感性要求一个截然不同的设计：

| | Research Verifier Loop | 聊天 Reflection |
|---|---|---|
| 延迟容忍 | 秒级，2 轮迭代可接受 | 毫秒级，不能阻塞 user 看到回答 |
| 反馈长度 | 完整报告 + citation 审计 | 单句判断 + 关键遗漏 |
| 副作用 | 生成新内容（patch/rewrite） | 写入记忆（供未来参考） |
| 循环 | 可能需要 2-3 轮迭代 | 1 次判断即结束 |

所以聊天 Reflection 不是"简化版 Verifier Loop"，而是一个**独立的设计**：异步非阻塞、1-shot 判断、副作用写记忆。

**约束**：
- 不能增加用户感知延迟（反思在 answer 流式返回后再执行）
- 不能修改已发送的 answer 内容（反思只在下一轮影响行为）
- 反思任务必须是 fire-and-forget（聊天 BG task 不能等反思结果）
- 不使用 Reflection 的重模型（如 Claude Opus），复用聊天模型或单独配置轻量模型

## Goals / Non-Goals

**Goals:**
- 回答流式完成后，触发一次异步 self-check
- 3 维判断：完整性、工具利用、用户满意度
- 反思结果追加到 `memory_text`，附时间戳
- `memory_text` 中的反思作为角色经验，注入下一轮 system prompt
- 反思失败不影响主流程（静默降级）

**Non-Goals:**
- 不做 multi-turn 迭代反思（1-shot 足够）
- 不修改已发送的 answer
- 不做跨模型验证（resource 不划算）
- 不改变现有 Celery 任务队列结构（用独立的后台协程）

## Decisions

### 决策 1：异步非阻塞 Fire-and-Forget

**选择**：反思任务使用 `asyncio.create_task()` 在 BG task 内部启动，不等待结果。写入 `memory_text` 使用独立 DB session。

```python
async def _run_chat_turn_bg(...):
    # ... 正常聊天流程 ...
    await bus.publish("done", ...)
    
    # fire-and-forget reflection
    if settings.chat_reflection_enabled:
        asyncio.create_task(_reflect_and_persist(
            persona_id, user_message, assistant_answer, tool_calls_log
        ))
```

**理由**：用户已经收到了完整回答，反思不应该成为下一轮交互的阻塞因素。用 `asyncio.create_task` 而非 Celery 任务是因为反思需要的是同一进程内的轻量 LLM 调用，不需要跨 worker 调度。BG task 的 `_BG_TASKS` set 已经防止 GC。

### 决策 2：3 维 Self-Check Prompt

**选择**：反思 prompt（`prompts/chat_reflection.jinja2`）：

```
你是角色 "{persona_name}" 的自我反思器。刚刚你回答了用户的问题。
请从以下 3 个维度简要评估你的回答（每个维度 1-2 句话）：

1. 完整性：有没有遗漏用户问题中的关键信息？
2. 工具利用：有没有该用但没调用的工具？用了的工具参数是否合理？
3. 用户满意度：回答是否直接命中了用户意图？语气是否符合角色人设？

输出格式（严格 JSON）：
{
  "completeness": "简要评估",
  "tool_usage": "简要评估", 
  "user_satisfaction": "简要评估",
  "key_takeaway": "一句话经验教训，供下次参考（如果回答很好，写'本次回答无问题'）",
  "should_remember": true/false
}

如果回答很好无需反思，key_takeaway 写"本次回答无问题"，should_remember 为 false。
```

**理由**：3 个维度覆盖了"漏东西""忘工具""答非所问"三种最常见的 LLM 回答缺陷。`should_remember` 标志位防止"无意义的反思"堆满 memory_text。JSON 输出便于结构化写入和未来按维度检索。

### 决策 3：memory_text 反思块格式

**选择**：反思追加到 `memory_text` 末尾，用 `---` 分隔：

```markdown
--- reflection 2026-07-14T15:30:00 ---
**对话**: 用户询问 Python 和 Go 的性能对比
**完整性**: 涵盖了 CPU 密集型场景，遗漏了内存管理差异
**工具利用**: 使用了 knowledge_search，但可以补充 web_search 获取最新 benchmark
**经验**: 性能对比类问题需要覆盖：CPU、内存、并发、生态四个维度
---
```

最新 10 条反思注入 system prompt（在"相关经验"区块）。

**理由**：`---` 是 Markdown 水平线，天然分隔。格式包含时间戳、对话摘要、三维评估、经验教训，未来可做结构化解析。限制注入 10 条避免 prompt 膨胀——10 条反思约 500-1000 token。

### 决策 4：反思触发条件

**选择**：以下情况**不触发**反思：
- 用户消息是纯闲聊（"你好""谢谢""再见"），由 `_is_trivial_message()` 判断（复用 active_recall 的 trivial message 检测）
- 回答未使用任何工具且长度 < 50 字（简单问题，自我检查意义不大）
- 回答过程中已抛出异常（无内容可反思）

**理由**：避免无意义的反思消耗 LLM 调用和 token。闲聊和极短回答的场景下，反思的信息量为零。

### 决策 5：反思不影响当前 answer

**选择**：反思结果**不**触发 answer 修改或重新生成（与 Research Verifier Loop 的 repair 截然不同）。

**理由**：聊天的延迟无法承受"反思 → 修改 → 重新生成"。反思的价值体现在"未来"——下一次类似问题出现时，角色能从经验中受益。参考 PreFlect (2026) 的前瞻反思哲学——反思的目的不是修正过去，而是优化未来。

## Risks / Trade-offs

- **[反思质量低]** 同模型 self-critique 有确认偏误风险（容易给自己打高分）→ **缓解**：(1) prompt 中 "宁严不松" 的设定参考了 Research Verifier 的设计；(2) `should_remember=false` 让无价值的反思不写入记忆；(3) 未来 Phase 可选升级为 CrossModelReflector（用独立的 verifier 模型）
- **[memory_text 膨胀]** 长期大量反思可能让 memory_text 过长 → **缓解**：(1) `should_remember=false` 过滤了大量内容；(2) 只注入最近 10 条到 system prompt；(3) 总大小限制 50000 字（已有 schema 限制）
- **[asyncio.create_task 可靠性]** Fire-and-forget 任务的异常不会传播到调用方 → **缓解**：`_reflect_and_persist()` 内部完整 try/except，失败只写 warning 日志
