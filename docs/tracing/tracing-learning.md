# SoulChat Agent 全链路轨迹追踪 — 从零学习

## 目录

1. [为什么要做追踪](#1-为什么要做追踪)
2. [核心概念：Trace 和 Span](#2-核心概念trace-和-span)
3. [Python 前置知识](#3-python-前置知识)
4. [架构总览](#4-架构总览)
5. [完整代码走读](#5-完整代码走读)
6. [并行场景分析](#6-并行场景分析)
7. [Token 来源和成本计算](#7-token-来源和成本计算)
8. [落库机制](#8-落库机制)
9. [前端怎么用](#9-前端怎么用)
10. [关键源码索引](#10-关键源码索引)

---

## 1. 为什么要做追踪

普通 Web 应用的一次请求很简单：收到请求 → 查数据库 → 返回结果。每一步做什么很清楚。

SoulChat 里一次对话请求（比如用户对"投资分析师"角色说："帮我分析一下我最近的投资偏好，顺便拉一下最近一周 A 股大盘数据，写一份简短的周报"），内部实际发生的事情远比看上去复杂：

```
收到问题
  → 调 LLM 理解意图（一次 API 调用）
  → LLM 决定并行执行：
    ├── 调 knowledge_search 查知识库中的持仓/交易记录（embedding + ES 检索）
    ├── 调 memory_search 从记忆图谱查用户投资偏好（embedding + Neo4j 查询）
    └── 调 web_search 查最近一周 A 股大盘数据（调联网搜索 API）
  → 三个工具并行执行完毕，结果回灌
  → LLM 判断需要更专业的分析 → 调 agent__数据研究员（角色互调）
    └── "数据研究员"以完整 Agent 身份独立运行：
        ├── 调 knowledge_search 查历史数据
        ├── 调 LLM 做统计分析
        └── 返回分析结论给主角色
  → LLM 判断需要写作能力 → 调 skill_load 加载"周报生成"Skill
  → Skill 返回提示词 + 脚本路径
  → 调 bash 工具执行脚本 python generate_report.py {...}
  → 脚本执行完毕返回 markdown
  → LLM 基于所有结果组织最终回答
  → 返回给用户
```

中间涉及：多次 LLM API 调用、embedding 调用、ES/Neo4j 查询、联网搜索 API、子 Agent 调用、Skill 脚本执行。如果没有追踪，你只能知道"总共花了 8 秒"，但不知道为什么——哪一步最慢？哪个模型调了最多次？角色互调的链路是否正常？Skill 脚本执行了多久？如果没有追踪，排查全靠猜。

追踪的目的就是**把一次请求内部的每一步单独记录下来**，事后可以回答这些问题：

- 这次请求总共调了几次 LLM？
- 每次 LLM 调用花了多少 token、多少时间、多少钱？
- 工具调用和 LLM 调用的嵌套关系是什么？（哪个工具里调了 LLM）
- 有没有步骤失败了？
- 并行执行的两个分支各自走了多久？

---

## 2. 核心概念：Trace 和 Span

### Trace（轨迹）

一次完整的用户请求就是一个 Trace。比如用户发了一条对话消息，从请求进来到回答返回，这整个过程是一个 Trace。

Trace 是一个"大容器"，存储这次请求的汇总信息：

| 字段 | 含义 |
|------|------|
| trace_id | 唯一标识 |
| task_type | 类型：chat / research / agent_task |
| total_input_tokens | 所有 LLM 调用输入 token 总计 |
| total_output_tokens | 所有 LLM 调用输出 token 总计 |
| total_cost_cny | 所有 LLM 调用费用总计（人民币） |
| duration_ms | 总耗时（毫秒） |
| root_span_id | 指向根 Span，前端从它开始构建树 |

### Span（片段）

Trace 内部的每一步操作就是一个 Span。

| 字段 | 含义 |
|------|------|
| span_id | 唯一标识 |
| parent_span_id | 父 Span 的 id（指向上一层的 Span） |
| trace_id | 属于哪个 Trace |
| span_type | 类型标签 |
| name | 人类可读的名字 |
| duration_ms | 该步耗时 |
| model_name | 如果这步调了 LLM，用的是什么模型 |
| input_tokens / output_tokens / cached_tokens | token 用量 |
| cost_cny | 这步花了多少钱 |
| payload | 输入输出的摘要（不存全文） |
| attributes | 语义属性键值对 |
| status | ok / error |

### span_type 的取值

代码里定义的 Span 类型标签：

| 值 | 含义 | 示例 |
|----|------|------|
| `llm_call` | LLM 推理调用 | chat / embedding / vision |
| `tool_call` | 内置工具调用 | 知识库检索、记忆检索 |
| `mcp_call` | MCP 协议工具调用 | 外接 MCP server 的工具 |
| `agent_call` | Agent 互调 | 角色 A 调角色 B |
| `planner` | 规划阶段 | 深度研究的规划步骤 |
| `retriever` | 检索阶段 | 深度研究的多源检索 |
| `writer` | 写作阶段 | 深度研究的分节写作 |
| `verifier` | Verifier Loop 审稿 | 质量打分 |
| `repair` | Verifier Loop 修复 | Patch 或章节重写 |

### 父-子关系形成树

每个 Span 记录自己的 `parent_span_id`，指向上一层 Span 的 id。根的 `parent_span_id` 为空。

SoulChat 里一次真实对话的 Trace 树可能是这样的（用户对投资分析师角色说"帮我分析投资偏好 + 写周报"）：

```
Trace(AAA, task_type="chat", persona="投资分析师")
│
├── span_主动召回 (type=retriever, parent=None)
│   ├── span_查记忆 (type=llm_call, name="embed:text-embedding-v3")   ← 向量化用户问题
│   └── span_读图谱 (type=llm_call, name="chat:deepseek-chat")        ← Neo4j Cypher 查询
│
├── span_编排器 (type=orchestrator, parent=None)
│   │
│   ├── span_第1轮工具调用 (并行执行)
│   │   ├── span_工具:knowledge_search (type=tool_call, parent=编排器)
│   │   │   └── span_embed (type=llm_call, name="embed:text-embedding-v3")
│   │   ├── span_工具:memory_search (type=tool_call, parent=编排器)
│   │   │   ├── span_embed (type=llm_call, name="embed:text-embedding-v3")
│   │   │   └── span_查图谱 (type=llm_call, name="chat:deepseek-chat")
│   │   └── span_工具:web_search (type=tool_call, parent=编排器)
│   │       └── span_联网 (type=llm_call, name="chat:deepseek-chat")  ← 调联网搜索 API
│   │
│   ├── span_第2轮工具调用
│   │   └── span_工具:agent__数据研究员 (type=agent_call, parent=编排器)
│   │       ├── span_工具:knowledge_search (type=tool_call)          ← 子Agent 自己的工具
│   │       │   └── span_embed (type=llm_call, name="embed:...")
│   │       ├── span_chat:分析推理 (type=llm_call, name="chat:deepseek-chat")
│   │       └── span_chat:最终输出 (type=llm_call, name="chat:deepseek-chat")
│   │
│   ├── span_第3轮工具调用
│   │   ├── span_工具:skill_load (type=tool_call, parent=编排器)     ← 加载写作 Skill
│   │   └── span_工具:bash (type=tool_call, parent=编排器)           ← 执行 Skill 脚本
│   │       └── span_subprocess:python generate_report.py (type=other)
│   │
│   └── span_最终回答 (type=llm_call, name="chat:deepseek-chat")    ← 综合所有结果
│
└── span_自我反思 (type=other, name="ChatReflector")                  ← 异步反思不阻塞
    └── span_chat:反思评分 (type=llm_call, name="chat:deepseek-chat")
```

前端拿到这些数据后，按 `parent_span_id` 就能重建这棵树，画成 Gantt 时间线图——并行执行的两个工具会重叠显示，Agent 互调的嵌套层级一目了然，Skill 脚本的执行时长单独可见。

---

## 3. Python 前置知识

### 3.1 `with`：普通的上下文管理器

`with` 让你在进入一个代码块时自动做一件事，退出时自动做另一件事（不论中间是否报错）。

```python
# 不用 with：手动管理文件
f = open("a.txt")
try:
    content = f.read()
finally:
    f.close()    # 必须手动关

# 用 with：自动管理
with open("a.txt") as f:
    content = f.read()
# 退出时自动调 f.close()，不管中间是否报错
```

`with obj as x` 的背后机制：
- 进入时：调 `obj.__enter__()`，返回值赋给 `x`
- 退出时：调 `obj.__exit__()`，做清理

### 3.2 `async with`：异步的上下文管理器

`with` 的进入和退出方法（`__enter__`/`__exit__`）里不能写 `await`。

`async with` 解决了这个问题——进入和退出方法（`__aenter__`/`__aexit__`）里可以 `await`：

```python
# async with 进入时可以 await 异步操作
async with async_db.connect() as conn:
    await conn.execute("SELECT ...")
# 退出时自动 await conn.close()
```

SoulChat 的 tracing 用 `async with` 不是因为退出时需要 `await`，而是为了**语义统一**——整个系统跑在 asyncio 里，所有上下文管理器都用异步版本。

### 3.3 `@asynccontextmanager`：让函数直接变成 `async with` 可用

Python 标准库 `contextlib` 提供。正常情况下，要让一个对象支持 `async with`，你需要写一个类并实现 `__aenter__` 和 `__aexit__`。

`@asynccontextmanager` 让你不用写类，直接写一个函数：

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def my_span(name):
    print(f"[进入] {name}")          # async with 进来时执行
    try:
        yield "返回值"               # yield 给 async with ... as x 里的 x
        # 正常走完到这里
        print(f"[成功] {name}")
    except Exception as e:
        # 中间代码抛异常了会到这里
        print(f"[失败] {name}: {e}")
        raise                        # 继续往外抛
    finally:
        print(f"[退出] {name}")      # 无论如何都会执行

# 使用
async with my_span("测试") as x:
    print(f"里面: {x}")
    # 如果这里抛异常，[失败] 和 [退出] 都会执行

# 输出：
# [进入] 测试
# 里面: 返回值
# [成功] 测试
# [退出] 测试
```

**三个关键位置**：

```
@asynccontextmanager
async def span():
    # 位置 A：yield 之前 = 进入时执行（相当于 __aenter__）
    yield handle
    # 位置 B：yield 之后 = 退出时执行（相当于 __aexit__）
    # 不管中间正常还是异常，finally 里的代码都会执行
```

### 3.4 ContextVar：协程安全的"小黑板"

Python 3.7 起内置的标准库 `contextvars.ContextVar`。

**问题**：多个 asyncio 协程同时跑，如果用一个普通全局变量存"当前状态"，B 协程会覆盖 A 协程的值。

**解决**：ContextVar 给每个协程分配一块独立的存储。你在自己的协程里写，别的协程看不到。

```python
from contextvars import ContextVar

current = ContextVar("current")

async def task_a():
    current.set("A的值")
    await asyncio.sleep(0.1)
    print(current.get())   # → "A的值"（不受 task_b 影响）

async def task_b():
    current.set("B的值")
    print(current.get())   # → "B的值"

await asyncio.gather(task_a(), task_b())
# 输出：
# B的值
# A的值
```

**关键行为**：用 `asyncio.create_task()` 或 `asyncio.gather()` 创建新协程时，Python 会把父协程的 ContextVar **拷贝一份**给子协程。拷贝后父子各自独立，互不影响。但拷贝的是**引用**——如果变量指向一个对象（比如一个列表或自定义类实例），父子指向的还是**同一个对象**。修改对象的属性两边都可见；替换变量本身则互不可见。

这在 tracing 里的应用：

```python
# 父协程设了 current_span = span_orch
# 然后 asyncio.gather(task_a, task_b)
#
# task_a 拷贝到 current_span = span_orch（快照）
#   → task_a 内部：current_span = span_tool_A（改自己的，不影响 task_b）
# task_b 拷贝到 current_span = span_orch（快照）
#   → task_b 内部：current_span = span_tool_B（改自己的，不影响 task_a）
#
# 但是！current_trace 指向的是同一个 Trace 对象
# → task_a 和 task_b 都往同一个 Trace 对象上累加 token 总量 ✅

有个地方需要注意：
在 tracing 里，_current_trace 和 _current_span 行为刚好相反，分别说明两种场景：

_current_trace：多个 Task 需要共享同一个对象

_current_trace: ContextVar = ContextVar("trace")
父子协程的 _current_trace 都指向堆上同一个 TraceRecord 实例：

堆上只有一个对象:
  TraceRecord(id=AAA, total_input_tokens=0, total_cost_cny=0)
      ↑               ↑               ↑
      |               |               |
  父协程的          Task A 的        Task B 的
  _current_trace   _current_trace   _current_trace
所以 Task A 执行 sp.set_tokens(input=500) → 同一个 Trace 对象上 total_input_tokens += 500。Task B 也在同一个对象上累加。最终汇总正确。

为什么不会冲突？ 因为三个协程都是在读同一个对象的属性和做加法，没有谁在替换引用本身。_current_trace 这个 ContextVar 的值（指向 TraceRecord 的指针）在整个 trace 生命周期里没被改过——协程只改了 TraceRecord 对象内部的字段。

_current_span：每个 Task 需要独立的 Span

_current_span: ContextVar = ContextVar("span")
初始状态，父子都指向同一个 Span（比如 span_编排器）：

堆上:
  SpanRecord(id=span_编排器, parent=None)
      ↑               ↑
      |               |
  父协程的          Task A/B 的
  _current_span    _current_span
但 Task A 一进入 tracer.span("工具:knowledge_search")，就调了 _current_span.set(新Span)——替换了自己的指针：


# tracer.py:211
span_token = _current_span.set(record)   # 把指针从 span_编排器 改成 span_knowledge_search

堆上:
  SpanRecord(id=span_编排器)          SpanRecord(id=span_knowledge_search)
      ↑                                       ↑
      |                                       |
  父协程/Task B 的                        Task A 的
  _current_span                          _current_span    ← 替换了！指向新对象
Task B 的 _current_span 仍然指向 span_编排器，因为 Task B 的 ContextVar 是独立拷贝，Task A 的 set() 不会影响它。

退出 async with 时，finally 块调 _current_span.reset(span_token)，恢复到上一个值——因为每个协程的 ContextVar 独立维护自己的"当前值→上一个值"的恢复链。
```

### 3.5 `asyncio.gather`：并行执行多个协程

```python
# 串行：B 必须等 A 完成
await task_a()
await task_b()

# 并行：A 和 B 同时跑，等两个都完成
await asyncio.gather(task_a(), task_b())
```

内部机制：`gather` 为每个参数创建一个 asyncio Task。创建 Task 时自动拷贝父协程的 ContextVar 快照。

---

## 4. 架构总览

SoulChat tracing 由 6 个文件组成，按职责分三层：

```
┌─────────────────────────────────────────────────┐
│  业务层（埋点）                                    │
│  LLMClient、orchestrator、engine.py              │
│  只需一行：async with tracer.span(...) as sp:    │
└────────────────────┬────────────────────────────┘
                     │ 调用
┌────────────────────▼────────────────────────────┐
│  核心层                                           │
│  tracer.py    → Tracer 单例，管理 span 栈         │
│  models.py    → SpanRecord / TraceRecord 数据结构 │
│  pricing.py   → 模型单价表，按 token 算成本        │
└────────────────────┬────────────────────────────┘
                     │ 关闭 span 时入队
┌────────────────────▼────────────────────────────┐
│  存储层                                           │
│  span_recorder.py → 异步批量写 PG                │
│  otel_attrs.py    → 属性名常量（对齐 OTel 标准）   │
└────────────────────┬────────────────────────────┘
                     │
              ┌──────▼──────┐
              │  PostgreSQL │
              │ agent_traces│
              │ agent_spans │
              └─────────────┘
```

设计原则（来自 [`__init__.py`](api/app/core/agent/tracing/__init__.py)）：

1. **非侵入** —— 业务代码只需一行 `async with tracer.span("名字") as sp:` 包裹即可
2. **不阻塞** —— Span 数据进内存队列，后台批次写 PG。写库失败只打日志不影响业务
3. **关闭即零开销** —— `tracing_enabled=False` 时所有 API 返回空壳对象，无任何计算
4. **兼容 OTel 标准** —— 属性名用 `gen_ai.*` 前缀，与 OpenTelemetry GenAI 规范对齐

---

## 5. 完整代码走读

### 5.1 入口：开启一个 Trace

业务代码首先调用 `tracer.trace()` 开始一次追踪：

```python
# 在 chat_service.py 或 engine.py 中
async with tracer.trace(
    user_id=user_id,
    task_type="chat",
    task_id=conv_id,
    task_name=user_text[:120],
) as tctx:
    # tctx.trace_id 是一个 UUID，可以通过 SSE 发给前端
    yield {"type": "trace", "trace_id": str(tctx.trace_id)}

    # ... 内部的所有操作都在这个 Trace 里 ...
```

**源码**（[tracer.py:134-183](api/app/core/agent/tracing/tracer.py#L134-L183)）：

```python
@asynccontextmanager
async def trace(self, user_id, task_type, task_id=None, ...):
    # ── 采样判断：没开 tracing 或没抽中 → 返回空壳，零开销 ──
    if not settings.tracing_enabled or random.random() > settings.tracing_sample_rate:
        yield _NoopTraceCtx()    # 空壳，所有方法都是 no-op
        return

    # ── 创建 Trace 记录 ──
    record = TraceRecord(
        user_id=user_id,
        task_type=task_type,
        task_id=task_id,
        started_at=datetime.now(),
    )
    # 把 Trace 设为当前协程的"活动 trace"
    trace_token = _current_trace.set(record)

    # 先把 trace 基本信息入库（create 事件）
    get_recorder().push_trace_create(record)

    try:
        yield _TraceCtx(record)          # ← 业务代码在 yield 期间执行
        #中文"句柄"是从英文 handle 直译过来的，本质就是一个让你间接操作某个东西的小物件。
        #Tracer 是引擎，负责创建/管理 trace 和 span 的生命周期。它是全局单例，你永远不会直接 new 一个 Tracer。_TraceCtx 是 tracer.trace() 返回给业务代码的句柄。业务代码通过这个句柄读 trace_id、设置属性，但不会接触 Tracer 本身的任何内部逻辑。
		#为什么不能直接把 TraceRecord 返回给业务代码？因为开了 tracing 和没开 tracing（或没被采样）时，返回的必须是一个有同样接口的对象，否则业务代码到处要写 if tctx is not None: XX
        record.status = "ok"
    except Exception as e:
        record.status = "error"
        record.error_message = str(e)
        raise
    finally:
        # 退出时：记录结束时间 + 总耗时 + 入队更新
        record.finished_at = datetime.now()
        record.duration_ms = (结束时 - 开始时) 的毫秒数
        get_recorder().push_trace_update(record)
        # 恢复 ContextVar：清除当前 trace
        _current_trace.reset(trace_token)
```

这个函数用 `@asynccontextmanager` 实现了三步生命周期：

```
进入（yield 之前）：创建 Trace → 写 ContextVar → 入队 create 事件
    执行业务代码（yield 期间）
退出（yield 之后）：设 finished_at/duration_ms → 入队 update 事件 → 恢复 ContextVar
```

用 `try...except` 保证了如果业务代码抛异常，Trace 会标记为 `status=error` 并记录错误信息，然后继续抛出异常，不影响上层错误处理。

### 5.2 核心：开启一个 Span

在 Trace 内部，各业务代码用 `tracer.span()` 记录每一步：

```python
async with tracer.span("工具:知识库搜索", span_type="tool_call") as sp:
    sp.set_payload("query", "上海天气")    # 记录输入
    result = await do_search(...)
    # 如果这里抛异常，span 会标记为 error
```

**源码**（[tracer.py:185-231](api/app/core/agent/tracing/tracer.py#L185-L231)）：

```python
@asynccontextmanager
async def span(self, name, span_type="other", attributes=None):
    # ── 没有 active trace 或 tracing 关了 → 返回空壳 ──
    tr = _current_trace.get()
    if not settings.tracing_enabled or tr is None:
        yield _SpanHandle(None)     # 空壳，所有操作都是 no-op
        return

    # ── 读"当前 Span"作为父节点 ──
    parent = _current_span.get()
    record = SpanRecord(
        trace_id=tr.trace_id,
        parent_span_id=parent.span_id if parent else None,  # 有父→记父id，没有→根span
        span_type=span_type,
        name=name,
        started_at=datetime.now(),
        attributes=attributes or {},
    )

    # 如果是第一个 Span（根节点），回填 Trace 的 root_span_id
    if parent is None and tr.root_span_id is None:
        tr.root_span_id = record.span_id

    # 把自己设为"当前 Span"——子 Span 会把我当父节点
    span_token = _current_span.set(record)
    handle = _SpanHandle(record)

    try:
        yield handle       # ← 业务代码执行，可以通过 handle 设属性/token
        if record.status == "running":
            record.status = "ok"
    except Exception as e:
        record.status = "error"
        record.error_message = str(e)[:1000]
        raise
    finally:
        # ── 退出时：记录结束时间 + 入队 + 恢复父 Span ──
        record.finished_at = datetime.now()
        record.duration_ms = (结束时 - 开始时) 的毫秒数
        get_recorder().push_span(record)
        _current_span.reset(span_token)     # 恢复为父 Span
```

**Tree 是怎么建起来的**：

```
第 1 步：进入 span_orch
  _current_span.get() → None
  创建 SpanRecord(parent_span_id=None)
  _current_span.set(span_orch)

第 2 步：在 span_orch 内部，进入 span_tool_A
  _current_span.get() → span_orch           ← 读到的就是父
  创建 SpanRecord(parent_span_id=span_orch)
  _current_span.set(span_tool_A)

第 3 步：在 span_tool_A 内部，LLMClient 调 LLM
  _current_span.get() → span_tool_A
  创建 SpanRecord(parent_span_id=span_tool_A)
  _current_span.set(span_llm)

第 4 步：LLM 调用结束，退出 span_llm
  _current_span.reset(span_token)           ← 恢复为 span_tool_A

第 5 步：工具调用结束，退出 span_tool_A
  _current_span.reset(span_token)           ← 恢复为 span_orch

... 以此类推，每层退出时自动恢复父节点
```

### 5.3 便捷方法：llm_span

LLM 调用是最频繁的 Span 类型，所以提供了一个快捷方法（[tracer.py:233-244](api/app/core/agent/tracing/tracer.py#L233-L244)）：

```python
@asynccontextmanager
async def llm_span(self, name, model_name=None, attributes=None):
    async with self.span(name, span_type="llm_call", attributes=attrs) as sp:
        if model_name and not sp.is_noop:
            sp._record.model_name = model_name   # 自动填模型名
        yield sp
```

等价于：

```python
async with self.span(name, span_type="llm_call") as sp:
    sp._record.model_name = model_name
    yield sp
```

### 5.4 SpanHandle：业务代码操作 Span 的接口

`async with tracer.span(...) as sp` 里的 `sp` 是一个 `_SpanHandle` 对象（[tracer.py:52-128](api/app/core/agent/tracing/tracer.py#L52-L128)），业务代码用它来记录信息：

```python
async with tracer.span("工具:知识库搜索", span_type="tool_call") as sp:
    # 记录属性键值对（给前端筛选和分组用的语义标签）
    sp.set_attribute("soulchat.tool.query", query[:200])

    # 记录 payload（输入输出的文本摘要，只存前几百字）
    sp.set_payload("query", query)
    sp.set_payload("output_chars", len(result))

    # 记录 token 用量（LLM 调用时用，自动查价格表算成本）
    sp.set_tokens(input=1500, output=300, cached=800, model_name="deepseek-chat")

    # 标记出错
    sp.mark_error("连接超时")

    # 判断是否为空壳（tracing 关了或没抽中时，避免做无用计算）
    if sp.is_noop:
        return
```

`set_tokens()` 的源码（[tracer.py:97-116](api/app/core/agent/tracing/tracer.py#L97-L116)）：

```python
def set_tokens(self, input=0, output=0, cached=0, model_name=None):
    if self._noop:
        return
    self._record.input_tokens = input
    self._record.output_tokens = output
    self._record.cached_tokens = cached
    if model_name:
        self._record.model_name = model_name

    # 按模型单价算成本
    self._record.cost_cny = estimate_cost_cny(model_name, input, output, cached)

    # 同时累加到上级 Trace
    tr = _current_trace.get()
    if tr is not None:
        tr.total_input_tokens += input
        tr.total_output_tokens += output
        tr.total_cost_cny += self._record.cost_cny
        if model_name and model_name not in tr.models_used:
            tr.models_used.append(model_name)
```

### 5.5 LLMClient：自动埋点

所有 LLM 调用都经过 `LLMClient`，所以在这里统一埋点。业务代码（萃取、记忆、研究等）调 `LLMClient` 时不需要自己写 `tracer.span`。

**以 `chat()` 方法为例**（[client.py:213-264](api/app/core/llm/client.py#L213-L264)）：

```python
async def chat(self, messages, temperature=0.3, max_tokens=2048):
    tracer = get_tracer()

    # 提取最后一条 user 消息做摘要
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = m.get("content", "")[:600]
            break

    async with tracer.llm_span(
        f"chat:{self.model_name}",
        model_name=self.model_name,
        attributes={
            "gen_ai.operation.name": "chat",
            "gen_ai.request.temperature": temperature,
        },
    ) as sp:
        sp.set_payload("messages_count", len(messages))
        sp.set_payload("request_summary", last_user)  # 记录问了什么

        # 发 HTTP 请求到 LLM API
        data = await _post_with_retry(
            f"{self.base_url}/chat/completions",
            headers=...,
            json={"model": self.model_name, "messages": messages, ...},
        )

        # 从 API 响应里提取 token 用量
        in_t, out_t, cached = _extract_usage(data)
        sp.set_tokens(input=in_t, output=out_t, cached=cached, model_name=self.model_name)

        # 记录回答摘要
        text = data["choices"][0]["message"]["content"]
        sp.set_payload("response_preview", text[:600])

        return text
```

LLM 调用的 Span 是由 `LLMClient` 自动创建的，不需要调 `LLMClient` 的代码再手动包一层。但如果是更上层的语义 Span（比如"编曲阶段在规划"），需要在上层代码里手动包 `tracer.span()`。Span 可以层层嵌套。

### 5.6 Orchestrator 里的工具 Span

Agent 编排器在执行工具时额外包了一层工具 Span（[orchestrator.py:207-208](api/app/core/agent/orchestrator.py#L207-L208)）：

```python
async def _exec_one(tool, args, name, query):
    t0 = time.monotonic()
    tr = get_tracer()
    async with tr.span(
        f"工具:{name}",
        span_type="tool_call",  # 或 mcp_call / agent_call
        attributes={
            "soulchat.tool.name": name,
            "soulchat.tool.query": str(query)[:200],
        },
    ) as tsp:
        observation = await tool.ainvoke(args)
        tsp.set_payload("output_chars", len(str(observation)))
        tsp.set_payload("output_preview", str(observation)[:600])

    latency_ms = int((time.monotonic() - t0) * 1000)
    return observation, status, latency_ms, stats
```

这样一笔工具调用产生的 Span 树就是：

```
span_tool (type=tool_call, name="工具:知识库搜索")    ← orchestrator 创建
  └── span_llm (type=llm_call, name="embed:...")      ← LLMClient 自动创建
```

---

## 6. 并行场景分析

这是最关键的场景。编排器发现知识库检索和记忆检索不互依赖，用 `asyncio.gather` 并行执行（[orchestrator.py:238](api/app/core/agent/orchestrator.py#L238)）：

```python
raw_list = await asyncio.gather(
    _exec_one(tool_A, args_A, "web_search", query_A),
    _exec_one(tool_B, args_B, "memory_search", query_B),
)
```

### 并行执行前的 ContextVar 状态

假设投资分析师决定了同时查三路信息——知识库、记忆、联网——互不依赖，可以并行。

编排器在 `_exec_one` 里为三个工具各开一个 `tracer.span(type="tool_call")`，这些 span 都创建在同一个父协程里。

```python
# orchestrator.py:238
raw_list = await asyncio.gather(
    _exec_one(tool_KB, args_KB, "knowledge_search", "用户持仓记录"),
    _exec_one(tool_Mem, args_Mem, "memory_search", "用户投资偏好"),
    _exec_one(tool_Web, args_Web, "web_search", "A股大盘一周走势"),
)
```

`asyncio.gather` 的内部机制：

1. 为三个 `_exec_one` 各创建一个 asyncio Task
2. 创建 Task 时，Python 自动把父协程的 ContextVar 拷贝一份给子 Task
3. 三份拷贝各自独立，互不影响

### 并行执行时的 ContextVar 状态

```
父协程的小黑板（asyncio.gather 之前）:
  _current_trace → Trace(id=AAA)
  _current_span  → span_编排器

asyncio.gather 创建三个 Task，各自拷贝：

Task A 小黑板:                      Task B 小黑板:                      Task C 小黑板:
  _current_trace → Trace(AAA)         _current_trace → Trace(AAA)         _current_trace → Trace(AAA)
  _current_span → span_编排器         _current_span → span_编排器         _current_span → span_编排器

Task A 进入 _exec_one:              Task B 进入 _exec_one:              Task C 进入 _exec_one:
  parent = span_编排器                parent = span_编排器                parent = span_编排器
  own = span_knowledge_search         own = span_memory_search            own = span_web_search
  _current_span = own                 _current_span = own                 _current_span = own

  内部再调 LLM:                      内部再调 LLM:                      内部再调 LLM:
    parent = own ← 正确!               parent = own ← 正确!               parent = own ← 正确!
    _current_span = span_embed         _current_span = span_chat           _current_span = span_chat

三个 Task 互不干扰——Task A 设了 span_embed 后，Task B 的 _current_span 仍然是 span_memory_search。


### 为什么 Trace 上的 Token 总量能正确汇总

三个 Task 都往 **同一个** `TraceRecord` 对象上累加 token。虽然 ContextVar 拷贝了引用，但拷贝的是"指向谁"的值——三个 `_current_trace` 都指向堆上同一个 `TraceRecord` 实例。

```
堆（内存）:
  TraceRecord(id=AAA, total_input_tokens=0, total_cost_cny=0)
      ↑           ↑           ↑
      |           |           |
Task A 的       Task B 的    Task C 的
_current_trace  _current_trace  _current_trace
```

Task A 里 `sp.set_tokens()` → Trace 对象上 `total_input_tokens += 500` → 变成 500
同时 Task B 里也在调 → 同一个对象上 `total_input_tokens += 300` → 变成 800
同时 Task C 里也在调 → 同一个对象上 `total_input_tokens += 200` → 变成 1000

最终 Trace 上的总量是三路汇总的结果。

### 最终落库的树和前端 Gantt 图

落库后 PG 里的 Span 记录（按 started_at 排序）：

```
span_编排器            parent=NULL     type=orchestrator   duration=7800ms
span_knowledge_search  parent=编排器   type=tool_call       duration=1200ms
  span_embed           parent=KB检索   type=llm_call        duration=300ms
span_memory_search     parent=编排器   type=tool_call       duration=1800ms
  span_embed           parent=记忆检索  type=llm_call        duration=350ms
  span_chat            parent=记忆检索  type=llm_call        duration=1100ms
span_web_search        parent=编排器   type=tool_call       duration=2500ms
  span_chat            parent=联网检索  type=llm_call        duration=2200ms
```

前端按 `parent_span_id` 重建树，画成 Gantt 图：

```
                               0    1s    2s    3s    4s    5s    6s    7s    8s
span_编排器                    ████████████████████████████████████████████████████
  span_knowledge_search          ████████
    span_embed                     ██
  span_memory_search                    ██████████████
    span_embed                           ███
    span_chat                                 █████████
  span_web_search                                  ██████████████████
    span_chat                                       ████████████████
```

**一眼能看出的信息**：
- 三个工具在时间线上有重叠——确认了它们确实是并行执行的
- 联网搜索最慢（2.5s），知识库最快（1.2s）——如果知识库的 embedding 模型换成更快的，整体延迟能缩短
- memory_search 里 embedding 和 chat 各占一部分——chat 是主要耗时
- 第一轮工具并行执行完后才进入下一轮（Agent 互调 + Skill），工具调用循环的迭代次数 = 3

### 6.5 角色互调 + Skill 执行的完整 Trace

并行工具执行完毕后，编排器继续进行后续的工具调用轮。其中最有 SoulChat 特色的是 Agent 互调和 Skill 执行。

**Agent 互调**：当 `agent__{name}` 工具被调用时，被调用角色以完整 Agent 身份运行。这个过程在 tracing 里反映为一棵嵌套的子 Agent 树：

```
span_工具:agent__数据研究员 (type=agent_call, name="agent__数据研究员")
├── span_编排器:chat:glm-4-flash (type=orchestrator)       ← 子Agent 自己的编排器
│   ├── span_工具:knowledge_search (type=tool_call)        ← 子Agent 调知识库
│   │   └── span_embed:text-embedding-v3 (type=llm_call)   ← 子Agent 的 embedding
│   ├── span_工具:memory_search (type=tool_call)            ← 子Agent 调记忆
│   │   ├── span_embed:text-embedding-v3 (type=llm_call)
│   │   └── span_chat:glm-4-flash (type=llm_call)
│   └── span_chat:glm-4-flash (type=llm_call)              ← 子Agent 最终回答
```

这个嵌套结构是自动形成的——子 Agent 内部调 `build_persona_agent()` 构建自己的 Agent 实例，用自己的 model/tools/system_prompt 跑完整的 function calling 循环。tracing 不需要特殊处理：子 Agent 在自己的协程里调 `tracer.span()`，ContextVar 自动保证了 `_current_span` 指向 `agent_call` 这个外层 Span，子 Agent 的所有 Span 自然成为它的子节点。

**Skill 执行**：`skill_load` 返回 Skill 的提示词和脚本清单后，Agent 调 `bash` 工具执行脚本。这个过程在 tracing 里也是嵌套的：

```
span_工具:skill_load (type=tool_call)
  └── span_chat:deepseek-chat (type=llm_call)               ← skill_load 内部查 DB

span_工具:bash (type=tool_call, name="bash:generate_report.py")
  └── span_subprocess:python generate_report.py (type=other)  ← 子进程执行追踪
```

**完整时间线**（前端 Gantt 图的效果）：

```
                        0    1s   2s   3s   4s   5s   6s   7s   8s   9s  10s
span_主动召回             ████
span_编排器               ██████████████████████████████████████████████████
  [第1轮] 并行工具
  knowledge_search          ███
    embed                    █
  memory_search               █████
    embed                     █
    chat                       ███
  web_search                        ██████
    chat                            █████
  [第2轮] Agent互调
  agent__数据研究员                     ████████████
    [子Agent内部]
    knowledge_search                    ███
    chat_推理                            ████
    chat_输出                                ███
  [第3轮] Skill执行
  skill_load                                        ██
  bash:generate_report.py                             ███
    subprocess                                         ██
  [最终] 综合回答
  chat:最终回答                                            ██████
span_自我反思                                                   ██
```

从这张图里可以看到：
- 总耗时约 10 秒，其中编排器占了绝大部分
- 第 1 轮的三工具确实并行执行了（时间线有重叠）
- Agent 互调花了约 4 秒——子 Agent 内部有自己的一套工具调用链
- Skill 脚本执行只花了约 2 秒——很快，不是瓶颈
- 自我反思是异步的，在主回答完成后才跑，不阻塞用户看到最终回答

---

## 7. Token 来源和成本计算

### 7.1 Token 从哪来

Token 数据不是 SoulChat 自己统计的，而是**LLM 厂商在 API 响应里返回的**。

每次调 LLM API（如 `POST /chat/completions`），服务器返回的 JSON 里包含 `usage` 字段：

```json
{
  "id": "chatcmpl-xxx",
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "明天上海气温..."
      }
    }
  ],
  "usage": {
    "prompt_tokens": 3500,
    "completion_tokens": 180,
    "prompt_tokens_details": {
      "cached_tokens": 2000
    }
  }
}
```

| 字段 | 含义 |
|------|------|
| `prompt_tokens` | 输入 token 数（你发给模型的全部内容） |
| `completion_tokens` | 输出 token 数（模型生成的回答） |
| `cached_tokens` | 这 3500 个输入 token 中有 2000 个命中了厂商的缓存 |

SoulChat 的 `_extract_usage()` 从响应中提取这三个数字（[client.py:111-125](api/app/core/llm/client.py#L111-L125)）：

```python
def _extract_usage(data):
    usage = data.get("usage") or {}
    input_tokens  = usage.get("prompt_tokens") or usage.get("total_tokens") or 0
    output_tokens = usage.get("completion_tokens") or 0
    details = usage.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens") or 0
    return input_tokens, output_tokens, cached
```

### 7.2 缓存命中是什么

不是 SoulChat 自己做了缓存。是 LLM 厂商（DeepSeek、OpenAI 等）的服务端缓存。

比如你的 system prompt 很长、历史消息很长，每次请求都发同样的内容，厂商识别出来后直接复用之前算过的中间结果，这些 token 不收钱或收折扣价。`cached_tokens` 就是命中了多少。

### 7.3 成本计算公式

`pricing.py` 里维护了一张模型单价表（[pricing.py:15-51](api/app/core/agent/tracing/pricing.py#L15-L51)），例如：

```python
"deepseek-chat": (0.002, 0.008, 0.0005),
#                 ↑input  ↑output ↑cached
#                 单位：CNY/千 token
```

计算公式（[pricing.py:57-80](api/app/core/agent/tracing/pricing.py#L57-L80)）：

```python
def estimate_cost_cny(model_name, input_tokens, output_tokens, cached_tokens):
    fresh_input = input_tokens - cached_tokens   # 真正新算的输入
    cost = (
        fresh_input    * input_price  / 1000.0   # 新输入成本
        + output_tokens * output_price / 1000.0  # 输出成本
        + cached_tokens * cached_price / 1000.0  # 缓存成本（折扣价）
    )
    return round(cost, 6)
```

例如一次 deepseek-chat 调用，输入 3500 token（其中 2000 缓存命中），输出 180 token：

```
cost = 1500×0.002/1000 + 180×0.008/1000 + 2000×0.0005/1000
     = 0.003 + 0.00144 + 0.001
     = 0.00544 元
```

模型名匹配支持前缀匹配：如果你配的模型名是 `deepseek-chat-v3-2025`，代码会自动匹配到 `deepseek-chat` 的单价。完全没命中则用兜底价 `(0.005, 0.015, 0.0025)`。

---

## 8. 落库机制

### 8.1 为什么不能直接写库

Span 是在热路径上创建的——一次对话可能产生 20+ 个 Span。如果每个 Span 退出时同步写 PG，主流程会被数据库延迟拖慢。所以用了"内存队列 → 批量写"的模式。

### 8.2 SpanRecorder 的工作流程

[span_recorder.py](api/app/core/agent/tracing/span_recorder.py)：

```
业务代码                      后台消费协程
  │                              │
  │ push_span(record)            │
  ├──→ asyncio.Queue ──→         │ 攒够一批或超时
  │ push_span(record)            │
  ├──→ asyncio.Queue ──→         ├── 批量 INSERT spans
  │                              ├── 批量 UPDATE traces
  │                              └── 继续等待下一批
  │ push_span(record)            │
  └──→ asyncio.Queue ──→         ...
```

关键参数（通过配置文件设置）：

| 参数 | 作用 | 典型值 |
|------|------|--------|
| `tracing_batch_size` | 攒够多少条就写一次 | 50 |
| `tracing_flush_interval` | 最多等多久写一次（秒） | 2 |
| `tracing_queue_maxsize` | 队列最大长度 | 5000 |

### 8.3 队列满和写库失败的处理

```python
def _enqueue(self, ev):
    try:
        self._queue.put_nowait(ev)
    except asyncio.QueueFull:
        # 队列满了：丢弃最旧的一条，放新的
        self._queue.get_nowait()     # 扔最旧的
        self._queue.put_nowait(ev)   # 放新的
        # 宁丢追踪数据，不卡业务
```

写库失败的处理：

```python
try:
    await self._flush(batch)
except Exception as e:
    logger.warning("SpanRecorder flush 失败,本批 %d 条丢弃: %s", len(batch), e)
    # 打日志 + 继续，不影响业务
```

### 8.4 零开销开关

当 `settings.tracing_enabled = False` 时，`tracer.span()` 的第一步就返回空壳 `_SpanHandle(None)`，所有 `sp.set_xxx()` 操作都是空的。不会创建 Span 对象，不会入队，不会写库，零 CPU 开销。

另外支持按比例采样（`tracing_sample_rate`），比如设为 0.1 则只有 10% 的请求被追踪。

---

## 9. 前端怎么用

前端拿到 trace_id 后，调 API 加载该 Trace 下的所有 Span，按 `parent_span_id` 建树，然后用 Gantt 时间线展示。

Tree 的重建逻辑（前端需实现）：

```
1. 加载所有 span（WHERE trace_id = ?）
2. 按 parent_span_id 分组
3. 从 parent_span_id = NULL 开始递归渲染
4. 同一个 parent 下的 span 按 started_at 排序
```

每条 Span 显示：
- 名称（如"工具:知识库搜索"）
- 耗时条（按 started_at 和 duration_ms 定位）
- 如果是 LLM Span：显示模型名、token 用量、成本
- 如果是工具 Span：显示工具名、查询内容（点击展开 payload）

可以下钻到单个 Span 看 `payload` 里的请求/回复摘要、`attributes` 里的语义标签。

并行 Span 在时间线上显示为重叠的横条（时间范围有交集），一眼能看出哪些调用是可以合并的。

---

## 10. 关键源码索引

| 文件 | 职责 |
|------|------|
| [tracer.py](api/app/core/agent/tracing/tracer.py) | Tracer 单例，trace()/span()/llm_span() 三个核心 API，SpanHandle 封装 |
| [models.py](api/app/core/agent/tracing/models.py) | SpanRecord 和 TraceRecord 数据结构定义 |
| [pricing.py](api/app/core/agent/tracing/pricing.py) | 40+ 模型单价表，按 token 计算 CNY 成本 |
| [span_recorder.py](api/app/core/agent/tracing/span_recorder.py) | 异步队列 + 批量写 PG，含队列满/写库失败的容错 |
| [otel_attrs.py](api/app/core/agent/tracing/otel_attrs.py) | OpenTelemetry GenAI 规范属性名常量 |
| [client.py:213-264](api/app/core/llm/client.py#L213-L264) | LLMClient.chat() 中的自动埋点 |
| [orchestrator.py:203-231](api/app/core/agent/orchestrator.py#L203-L231) | 工具并行执行 + 工具 Span 创建 |
| [research/engine.py](api/app/core/agent/research/engine.py) | 深度研究 6 阶段中各阶段 Span 的创建 |
| [loop/controller.py](api/app/core/agent/loop/controller.py) | Verifier/Repair Span 的创建 |
