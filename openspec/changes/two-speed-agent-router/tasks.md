## 1. AgentRouter 消息分类器

- [ ] 1.1 新建 `core/agent/router.py`：`AgentRouter` 类，`async def classify(message: str, available_tools: list[str]) -> RouteResult`
- [ ] 1.2 新建 `prompts/router.jinja2`：4 路分类 prompt（~200 token），输出严格 JSON
- [ ] 1.3 `RouteResult` Pydantic model：`route: Literal["trivial","chat","single_tool","multi_step"]`, `confidence: float`, `reason: str`
- [ ] 1.4 Router 用轻量模型（`build_router_model()` 从 settings.router_model 构建，默认 `gpt-4o-mini`）
- [ ] 1.5 Router 调用异常 → `RouteResult(route="single_tool", confidence=0, reason="router error")` （防御性回退）

## 2. MicroPlanner

- [ ] 2.1 新建 `core/agent/planner.py`：`MicroPlanner` 类，`async def plan(message: str, tools_summary: str) -> Plan`
- [ ] 2.2 新建 `prompts/planner.jinja2`：DAG 规划 prompt（工具列表 + 规划规则 + JSON schema 约束）
- [ ] 2.3 `Plan` 和 `PlanStep` Pydantic model：`goal: str`, `steps: list[PlanStep]`；`PlanStep` 含 `id, description, tool_hint, query_hint, dependencies, expected_output`
- [ ] 2.4 验证器：步骤 ≤ 4、深度 ≤ 2、无循环依赖、`dependencies` 中的 id 都存在于 steps 中
- [ ] 2.5 验证失败 → 抛 `PlanError`，调用方 fallback 到 `run_function_calling()`

## 3. DAGExecutor

- [ ] 3.1 新建 `core/agent/dag_executor.py`：`DAGExecutor` 类，`async def execute(plan, model, tools, messages, persona) -> dict[str, str]`
- [ ] 3.2 拓扑分层函数：`_topological_layers(steps) -> list[list[PlanStep]]`
- [ ] 3.3 并行层执行：`asyncio.gather(*[_execute_step(s, ...) for s in layer], return_exceptions=True)`
- [ ] 3.4 `_execute_step(step, context, prior_results)`：有 tool_hint 步骤走 `run_function_calling(max_iter=3)`，无 tool_hint 步骤走纯 LLM 综合
- [ ] 3.5 步骤内 events 透传：`step_start` / `step_done` + `tool_start`/`tool_result` 附加 `step_id`
- [ ] 3.6 DAG 执行超时：总超时 = 层数 × 每层超时（默认 60s/层）

## 4. 编排器集成

- [ ] 4.1 `orchestrator.py` 新增 `run_two_speed(model, tools, messages, persona, router_model)` → AsyncGenerator[dict]
- [ ] 4.2 实现路由分发逻辑（trivial → stream_plain, chat → stream_plain, single_tool → run_function_calling, multi_step → plan → execute → synthesize）
- [ ] 4.3 保留 `run_function_calling()` 和 `run_react()` 不变（作为 fallback）
- [ ] 4.4 `stream_plain()` 函数——纯 LLM 流式输出（已有代码路径，提取为独立函数）

## 5. 聊天服务集成

- [ ] 5.1 `services/chat_service.py` `_generate_events()`：将当前"三路 dispatch"改为调用 `run_two_speed()`
- [ ] 5.2 Router 在 `_generate_events()` 内构建（从 settings 读取配置）
- [ ] 5.3 `settings.two_speed_enabled` 开关控制是否启用 Two-Speed 路径（未启用时保持当前行为）

## 6. 配置 + 提示词

- [ ] 6.1 `config.py`：`two_speed_enabled: bool = True`，`router_model: str | None = None`
- [ ] 6.2 `prompts/planner.jinja2`：包含工具列表模板、DAG 约束说明
- [ ] 6.3 `prompts/dag_synthesize.jinja2`：综合步 prompt——"基于以下步骤的结果，生成最终回答"

## 7. 测试计划

### 7.1 单元测试 (`api/tests/test_agent_router.py`)

- [ ] 7.1.1 `test_router_classify_trivial`: "你好"→route="trivial", "谢谢"→"trivial", "今天天气不错"→"trivial"
- [ ] 7.1.2 `test_router_classify_chat`: "你觉得 Python 怎么样"→route="chat", "给我解释闭包"→"chat"
- [ ] 7.1.3 `test_router_classify_single_tool`: "帮我查知识库里关于 Python 的文档"→route="single_tool"
- [ ] 7.1.4 `test_router_classify_multi_step`: "比较 Python 和 Go 的性能，各找 3 个 benchmark，用表格输出"→route="multi_step"
- [ ] 7.1.5 `test_router_confidence_threshold`: confidence < 0.7 时记录 warning 日志（但路由结果照常使用）
- [ ] 7.1.6 `test_router_exception_fallback`: LLM 调用抛异常 → 返回 `RouteResult(route="single_tool", confidence=0)`，不传播异常
- [ ] 7.1.7 `test_router_model_reuse`: `router_model=None` 时复用聊天模型

### 7.2 单元测试 (`api/tests/test_micro_planner.py`)

- [ ] 7.2.1 `test_plan_step_limit`: 模拟 Planner 返回 6 步 → 验证器抛 `PlanError("步骤数超过 4")`
- [ ] 7.2.2 `test_plan_depth_limit`: 模拟 Planner 返回深度 3 的 DAG → 验证器抛 `PlanError("深度超过 2")`
- [ ] 7.2.3 `test_plan_cycle_detection`: 模拟 A→B→A 循环依赖 → 验证器抛 `PlanError("存在循环依赖")`
- [ ] 7.2.4 `test_plan_missing_dependency`: dependencies 引用了不存在的 step_id → 验证器抛 `PlanError`
- [ ] 7.2.5 `test_valid_plan_passes`: 合法的 ≤4 步 ≤2 层无环 DAG 通过验证，返回 `Plan` 对象
- [ ] 7.2.6 `test_empty_dependency_parallel`: 所有步骤 `dependencies=[]` → 全部在同一层，并行执行的 Coro 数量 = 步骤数

### 7.3 单元测试 (`api/tests/test_dag_executor.py`)

- [ ] 7.3.1 `test_topological_layers_two_layers`: 步骤 A/B(无依赖)、C(依赖A)、D(依赖B) → 层1=[A,B], 层2=[C,D]
- [ ] 7.3.2 `test_topological_layers_all_parallel`: 所有步骤无依赖 → 1 层全部
- [ ] 7.3.3 `test_topological_layers_sequential`: A→B→C→D 链式 → 4 层各 1 步
- [ ] 7.3.4 `test_execute_step_with_tool_hint`: tool_hint 步骤调用 `run_function_calling(max_iter=3)`（Mock 验证 max_iter）
- [ ] 7.3.5 `test_execute_step_without_tool_hint`: 无 tool_hint 步骤调用纯 LLM `model.ainvoke()`，不带工具
- [ ] 7.3.6 `test_execute_step_timeout`: 步骤执行超过 60s → 抛 `TimeoutError`，该 step 结果为 `"执行超时"`
- [ ] 7.3.7 `test_synthesize_step_receives_prior_results`: 综合步的 prompt 包含前序步骤的 `step_id → result` 映射

### 7.4 集成测试 (`api/tests/test_two_speed_orchestration.py`)

- [ ] 7.4.1 `test_trivial_route_no_tools`: 发送"你好" → Router→trivial → `stream_plain()` → 不调用 `build_enabled_tools()`（验证 Mock）
- [ ] 7.4.2 `test_chat_route_no_tools`: 发送"解释闭包" → Router→chat → `stream_plain()` → 不挂工具
- [ ] 7.4.3 `test_single_tool_route`: 发送"查知识库 Python 文档" → Router→single_tool → `run_function_calling()` 行为与改动前一致
- [ ] 7.4.4 `test_multi_step_e2e`: 发送"帮我比较 Python 和 Go 的性能，各找 3 个 benchmark，用表格输出" → Planner 生成 DAG → DAGExecutor 并行执行 → 综合步生成最终回答
- [ ] 7.4.5 `test_planner_failure_fallback`: Planner 返回无效 DAG → 自动 fallback 到 `run_function_calling()` → 正常回答（验证 fallback 触发）
- [ ] 7.4.6 `test_router_failure_fallback`: Router 抛异常 → fallback 到 `run_function_calling()`
- [ ] 7.4.7 `test_step_events_have_step_id`: multi_step 路径的 `tool_start`/`tool_result` 事件包含 `step_id` 字段

### 7.5 回归测试

- [ ] 7.5.1 `test_two_speed_disabled_unchanged`: `two_speed_enabled=false` → 完全走旧路径，行为和事件序列与改动前逐项对比无变化
- [ ] 7.5.2 `test_eval_gold_set_no_regression`: `uv run python -m eval.run_eval` gold-set 得分不降级
- [ ] 7.5.3 `test_hotpotqa_no_regression`: `uv run python -m eval.run_eval --benchmark hotpotqa` EM 得分不降级

### 7.6 性能验证

- [ ] 7.6.1 Router 延迟 p95 < 500ms（轻量模型 `gpt-4o-mini` 或同等，300-500ms 量级）
- [ ] 7.6.2 trivial/chat 路径延迟与改动前差异 < Router 开销（< 500ms）
- [ ] 7.6.3 multi_step 路径端到端延迟 ≤ 同任务走纯 ReAct（并行执行节省的时间 ≥ Planner 开销）
- [ ] 7.6.4 DAG 同层步骤 tool_start 时间戳差异 < 100ms（验证真正并行执行）

### 7.7 Lint

- [ ] 7.7.1 `uv run ruff check .` 无新增 lint 问题
