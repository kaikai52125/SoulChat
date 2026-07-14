## 1. Shared Blackboard

- [ ] 1.1 新建 `core/agent/blackboard.py`：`BlackboardEntry` (Pydantic) + `SharedBlackboard` 类
- [ ] 1.2 `SharedBlackboard.post(entry)` / `get_context_for(persona_name, max_entries)` / `summarize()`
- [ ] 1.3 黑板 entry 类型：`task`, `subtask`, `finding`, `draft`, `comment`, `decision`
- [ ] 1.4 黑板 summary 方法——提取所有 finding + decision 的核心要点（给 Verifier 用）

## 2. Task Orchestrator

- [ ] 2.1 新建 `core/agent/task_orchestrator.py`：`TaskOrchestrator` 类
- [ ] 2.2 `decompose(user_message, member_capabilities) -> TaskPlan`：LLM 分解任务 → 子任务列表（含角色指派 + 依赖关系）
- [ ] 2.3 新建 `prompts/task_orchestrator.jinja2`：任务分解 prompt
- [ ] 2.4 `execute(plan, blackboard, group_members)`：按拓扑分层层内并行执行子任务
- [ ] 2.5 `synthesize(blackboard) -> str`：汇总黑板中的所有 finding 为最终产出

## 3. Verifier 集成

- [ ] 3.1 新建 `core/agent/loop/rubric/collaboration.py`：协作产出 rubric（复用现有 6 维框架，调整权重）
- [ ] 3.2 `TaskOrchestrator` 的 synthesize 产出传入 `LoopController.run()` 进行审查
- [ ] 3.3 审查失败 → Patch repair（追加角色补充研究）

## 4. 群聊入口改造

- [ ] 4.1 `core/agent/group_chat.py` 新增 `_run_task_mode()` 函数——创建 Blackboard → TaskOrchestrator.decompose → execute → synthesize → verify → 返回
- [ ] 4.2 `run_group_chat()` 新增 `mode: Literal["social", "task"] = "social"` 参数
- [ ] 4.3 `services/group_chat_service.py`：API 路由新增 `mode` 参数，传递给 `run_group_chat()`
- [ ] 4.4 现有社交模式代码（`decide_speakers()`, `build_speaker_messages()` 等）完全不动

## 5. 数据模型

- [ ] 5.1 `models/group_message_model.py`：group_messages 新增 `task_role` 字段（nullable, enum: orchestrator/worker/verifier/user）
- [ ] 5.2 `migrations/`：alembic migration
- [ ] 5.3 `schemas/group_chat_schema.py`：ChatRequest 新增 `mode: str = "social"` 字段

## 6. 提示词

- [ ] 6.1 `prompts/task_orchestrator.jinja2`：任务分解模板（成员能力列表 + 分解规则 + JSON 输出约束）
- [ ] 6.2 `prompts/blackboard_summarizer.jinja2`：黑板内容结构化为最终报告的 prompt
- [ ] 6.3 `prompts/group_speaker.jinja2` 不变（任务模式下不使用 speaker prompt，使用 orchestrator prompt）

## 7. 前端

- [ ] 7.1 `GroupChatPage.tsx`：输入框旁新增模式切换 toggle（"社交🎭 / 任务🎯"）
- [ ] 7.2 任务模式激活时：右侧面板从"成员列表"切换为"黑板视图"（展示 subtask 状态 + 角色输出摘要）
- [ ] 7.3 任务模式 loading 状态：展示各角色执行进度（"研究员正在调研中..."）
- [ ] 7.4 任务完成时展示 Verifier 评分（可选，初版可隐藏）

## 8. 测试计划

### 8.1 单元测试 (`api/tests/test_shared_blackboard.py`)

- [ ] 8.1.1 `test_blackboard_post_and_retrieve`: post 3 条不同 type 的 entry → `get_context_for()` 返回全部 3 条，按时间戳排序
- [ ] 8.1.2 `test_blackboard_context_limit`: post 20 条 entry → `get_context_for(max_entries=10)` 只返回最近 10 条
- [ ] 8.1.3 `test_blackboard_summarize`: post 若干 finding + decision → `summarize()` 返回结构化摘要（含每条 finding 的核心要点）
- [ ] 8.1.4 `test_blackboard_entry_types_enum`: 传入非法 entry type 抛 ValidationError
- [ ] 8.1.5 `test_blackboard_empty_context`: 无 entry 时 `get_context_for()` 返回空字符串，不报错

### 8.2 单元测试 (`api/tests/test_task_orchestrator.py`)

- [ ] 8.2.1 `test_decompose_generates_valid_plan`: 输入"分析新能源汽车市场" + 3 个成员能力 → 返回 TaskPlan(subtasks 数量 ≥ 1，每个有 `assigned_persona`)
- [ ] 8.2.2 `test_decompose_respects_member_capabilities`: 成员能力描述含"数据分析" → 分析类 subtask 指派给该成员（而非含"写文章"的成员）
- [ ] 8.2.3 `test_decompose_single_member_fallback`: 只有 1 个成员时，所有 subtask 指派给该成员
- [ ] 8.2.4 `test_execute_parallel_independent_subtasks`: 3 个无依赖的 subtask → 并行执行（Mock 验证 `asyncio.gather` 被调用）
- [ ] 8.2.5 `test_execute_sequential_dependent_subtasks`: A→B→C 链式依赖 → 分 3 层串行执行（Mock 验证 gather 每次只含 1 个 task）
- [ ] 8.2.6 `test_execute_one_subtask_failure`: 一个 subtask 执行失败 → 其他 subtask 正常完成，失败 subtask 在黑板记录 `"执行失败：..."`

### 8.3 集成测试 (`api/tests/test_task_collaboration.py`)

- [ ] 8.3.1 `test_social_mode_unchanged`: 群聊 `mode="social"` → 完整对话流程：Host 选发言顺序 → 角色轮流发言 → 返回，行为与改动前完全一致
- [ ] 8.3.2 `test_task_mode_e2e`: 创建 3 人角色组（研究员/分析师/写手）→ `mode="task"` 发送"帮我分析新能源汽车市场" → Orchestrator 分解 → 黑板中产生各角色 finding → synthesize 返回综合报告
- [ ] 8.3.3 `test_blackboard_preserves_all_findings`: 任务完成后验证黑板中每个角色的 finding entry 都出现在最终产出中（不被截断/遗漏）
- [ ] 8.3.4 `test_verifier_review_in_task_mode`: 协作产出传入 `LoopController.run()` → 返回 verified artifact → 验证 rubric 各维度评分 ≥ 阈值
- [ ] 8.3.5 `test_verifier_repair_on_failure`: Verifier 评分不及格 → Patch repair 触发（追加角色补充研究）→ 二次验证分数提升

### 8.4 回归测试

- [ ] 8.4.1 `test_group_chat_api_unchanged_for_social_mode`: 群聊 API 不传 `mode` 参数 → 默认 `"social"`，所有现有测试用例通过
- [ ] 8.4.2 `test_group_messages_structure_unchanged`: 社交模式的消息存储格式不变（无 `task_role` 字段写入）

### 8.5 容错测试

- [ ] 8.5.1 `test_orchestrator_decompose_failure_fallback`: Orchestrator 分解任务失败（LLM 返回非法 JSON）→ 降级为单角色回答（取第一个成员直接回复用户）
- [ ] 8.5.2 `test_verifier_failure_does_not_block`: Verifier 审查抛异常 → 跳过验证，直接返回 orchestator 的 synthesize 结果
- [ ] 8.5.3 `test_blackboard_timeout_does_not_block`: 角色执行 subtask 超时 → 该角色在黑板中标记"超时"，其他角色继续

### 8.6 性能验证

- [ ] 8.6.1 任务模式端到端延迟：独立 subtask 并行执行，总延迟 ≈ max(各角色耗时) + Orchestrator 开销，而非 sum
- [ ] 8.6.2 黑板操作延迟：`post()` 和 `get_context_for()` 为纯内存操作，< 1ms

### 8.7 Lint

- [ ] 8.7.1 `uv run ruff check .` 无新增 lint 问题
