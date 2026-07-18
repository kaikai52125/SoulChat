## Why

当前 orchestrator 的 function calling 路径在遍历 `gathered.tool_calls` 时使用 `for tc in tool_calls: await tool.ainvoke(args)` 顺序执行。当 LLM 一次决定调用 3 个互不依赖的工具（如 knowledge_search + memory_search + web_search），这三个调用需要 T1+T2+T3 的累积延迟，而它们之间没有任何数据依赖。改成 `asyncio.gather` 并行执行，延迟从 "sum" 变为 "max"，多工具调用场景的端到端延迟显著降低。

ReAct 路径同理 —— 当前 `Action` 正则只捕获一个工具调用，但 ReAct prompt 实际上可以输出多个 Action 块。改为支持多 Action 解析 + 并行执行，让弱模型也能从并行中受益。

## What Changes

- `orchestrator.py` function calling 路径：`for` 循环改为 `asyncio.gather`，独立工具并行执行，有依赖的工具保持顺序（通过调用缓存天然处理）
- `orchestrator.py` ReAct 路径：`_ACTION_RE` / `_ACTION_INPUT_RE` 改为 `re.finditer` 提取多组 Action/Action Input，再 `asyncio.gather` 执行
- 并行组的工具结果全部返回后，统一追加 ToolMessage 回 messages 列表，继续下一轮 LLM 迭代
- 事件发射（`tool_start` / `tool_result`）保持串行以保证前端展示顺序确定
- 调用缓存 key 合并去重逻辑不变（同 turn 内相同参数调用只执行一次）

## Capabilities

### New Capabilities

- `parallel-tool-execution`: orchestrator function calling 路径支持并行执行独立工具调用，延迟从 sum(t_i) 降为 max(t_i)

- `react-multi-action`: ReAct 路径支持一轮输出多个 Action/Action Input 对，并行执行后统一观察

## Impact

- **orchestrator** (`core/agent/orchestrator.py`): 核心改动，仅改 `run_function_calling` 和 `run_react` 两个函数
- **代理层无影响**: 不改事件协议、不改工具接口、不改 chat_service，对外行为完全透明
- **前端无影响**: `tool_start` / `tool_result` 事件顺序和格式不变
