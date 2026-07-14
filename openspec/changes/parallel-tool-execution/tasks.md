## 1. function calling 路径并行化

- [ ] 1.1 `orchestrator.py` `run_function_calling()`：将 `for tc in gathered.tool_calls:` 循环内的 `tool.ainvoke(args)` 改为先收集所有 `(tool, args)` 到列表，再 `asyncio.gather(*coros, return_exceptions=True)` 批量执行
- [ ] 1.2 并行结果收集后，用 `for` 循环逐条做：`_format_observation()` → `yield tool_result` → 构造 `ToolMessage` → 追加到 messages
- [ ] 1.3 异常处理：`return_exceptions=True` 后每个结果 `isinstance(result, Exception)` 判断，失败的 observation = `"工具执行失败：{e}"`, status = `"error"`（与串行版一致）
- [ ] 1.4 调用缓存去重逻辑保持：并行前仍然检查 `call_cache`，命中的跳过不加入 `gather` 列表

## 2. ReAct 路径多 Action 解析 + 并行

- [ ] 2.1 `orchestrator.py` `run_react()`：将 `_ACTION_RE.search()` / `_ACTION_INPUT_RE.search()` 改为 `re.finditer` 提取所有匹配对
- [ ] 2.2 按出现顺序配对 Action 和 Action Input（相同数量的假设），短的截断
- [ ] 2.3 多 Action 收集完后 `asyncio.gather(*coros, return_exceptions=True)` 并行执行
- [ ] 2.4 Observation 合并为多段 → `HumanMessage(content=f"Observation 1: {obs1}\nObservation 2: {obs2}...")` 追加到 convo
- [ ] 2.5 无 Action 匹配时保持当前行为（整段文本当作 Final Answer）

## 3. 测试计划

### 3.1 单元测试 (`api/tests/test_parallel_execution.py`)

- [ ] 3.1.1 `test_gather_independent_tools`: Mock 3 个工具的 `ainvoke`（分别 sleep 100ms/200ms/150ms），验证 `asyncio.gather` 总耗时 ≈ max(100,200,150) = 200ms，而非 sum = 450ms
- [ ] 3.1.2 `test_return_exceptions_true`: 模拟 1 个工具抛 `ValueError`，验证其他 2 个正常返回，异常工具 observation 包含 `"工具执行失败：ValueError"`
- [ ] 3.1.3 `test_all_tools_fail`: 全部工具抛异常时，验证不传播异常，每条 observation 各自包含 error text
- [ ] 3.1.4 `test_cache_hit_skips_execution`: 同 turn 内第二次调用同一工具同一参数，验证 `call_cache` 命中，`tool.ainvoke` 未被调用（Mock 断言 `assert_not_called`）
- [ ] 3.1.5 `test_cache_key_deterministic`: 验证相同 args 不同顺序的 json.dumps 结果一致（`sort_keys=True`）
- [ ] 3.1.6 `test_event_order_maintained`: 并行执行后 event 发射仍按 tool_calls 原始顺序，`tool_start`→`tool_result` 交替不交错
- [ ] 3.1.7 `test_react_multi_action_parsing`: 模拟包含 3 组 Action/Action Input 的 LLM 输出，验证 `re.finditer` 正确提取 3 对
- [ ] 3.1.8 `test_react_single_action_backward_compat`: 单 Action 的旧格式输出仍然被正确解析（不因 `finditer` 改动而破坏）

### 3.2 集成测试

- [ ] 3.2.1 `test_e2e_parallel_knowledge_and_memory`: 通过 chat API 发送"同时查知识库的 Python 文档和记忆中的编程偏好"，抓取 `tool_start` 时间戳，验证 knowledge_search 和 memory_search 的启动时间差 < 50ms
- [ ] 3.2.2 `test_parallel_with_mcp_tools`: 同时调用内置工具 + MCP 工具，验证两种工具类型在 gather 中正常工作
- [ ] 3.2.3 `test_event_sequence_matches_spec`: 验证完整事件流 `[token...] → [tool_start → tool_result]×N → (optional) [token...] → final`，无意外事件类型

### 3.3 回归测试

- [ ] 3.3.1 `test_original_serial_behavior`: 当 `gathered.tool_calls` 只有 1 个时，行为与改动前完全一致（用 diff 对比事件序列）
- [ ] 3.3.2 `test_react_path_unchanged_for_single_action`: ReAct 路径单 Action 场景的 observation 格式不改动
- [ ] 3.3.3 `run_eval` gold-set 回归：`uv run python -m eval.run_eval --only retrieval` 得分不降级

### 3.4 性能验证

- [ ] 3.4.1 记录并行前后的 2-tool 场景延迟：改动前 T_knowledge + T_memory，改动后 max(T_knowledge, T_memory)，确认降低 ≥ 30%
- [ ] 3.4.2 验证并行对单工具场景无性能退化（差异 < 5ms）

### 3.5 Lint

- [ ] 3.5.1 `uv run ruff check .` 无新增 lint 问题
