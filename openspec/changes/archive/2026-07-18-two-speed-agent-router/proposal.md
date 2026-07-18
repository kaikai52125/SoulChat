## Why

当前聊天 Agent 循环是纯 ReAct——每一步都是 "LLM 推理 → 选 1 个工具 → 等待结果 → 再推理"，多步任务时延迟叠加、贪婪决策无全局视角。而 Research 模式已有 Pipeline 设计（Plan → Retrieve → Distill → Reflect → Curate → Write），证明多阶段规划在复杂任务上的优势。

Two-Speed Design 是 2025-2026 业界共识的混合架构：(1) 一个便宜的 Router 判断消息复杂度；(2) 多步任务走 Micro-Planner 生成 ≤4 步小 DAG；(3) DAG Executor 并行执行节点（每节点内仍用 ReAct）；(4) 简单任务直接走裸 LLM 或单工具 ReAct。核心原则是"只在需要时引入复杂度"。

这个 proposal 将 Research 的 Pipeline 设计经验降维应用到聊天场景，同时复用了并行工具执行（`parallel-tool-execution` change）和动态工具发现（`dynamic-tool-discovery` change）的能力。

## Dependencies

- **依赖 `parallel-tool-execution`**: DAG Executor 的并行节点执行依赖并行工具能力
- **依赖 `dynamic-tool-discovery`**: Router/Planner 判断任务复杂度时需知道"有哪些工具可用"

## What Changes

- 新增 `AgentRouter`（`core/agent/router.py`）——轻量消息分类器，4 路路由
- 新增 `MicroPlanner`（`core/agent/planner.py`）——多步任务时生成 ≤4 步小 DAG
- 新增 `DAGExecutor`（`core/agent/dag_executor.py`）——按 DAG 拓扑执行节点（并行层内所有节点，层间串行）
- `orchestrator.py` 新增 `run_two_speed()` 入口——Router → Planner → DAG Executor，替代当前的直接 `run_function_calling()`
- `chat_service.py` 调度路径改为先 `run_two_speed()`，兼容旧路径 `run_function_calling()` 作为 fallback
- Router 用 `gpt-4o-mini` 或同等轻量模型（可配置），Planner 复用聊天模型

## Capabilities

### New Capabilities

- `agent-routing`: 轻量消息分类器，4 路路由（trivial/chat/single_tool/multi_step）
- `micro-planning`: 多步任务自动拆解为 ≤4 步小 DAG（每步标注所需工具、输入、预期输出）
- `dag-execution`: DAG 拓扑执行器，同层节点并行执行，层间串行，支持 interrupt/pause

### Modified Capabilities

- `agent-orchestration`: 新增 `run_two_speed()` 作为主调度路径，现有 `run_function_calling()` 保留为 fallback
- `chat-pipeline`: `_generate_events()` 路由逻辑从三路（无工具/FC/ReAct）升级为四路（Router → Planner → DAG → FC/ReAct in-node）

## Impact

- **新文件** (`core/agent/router.py`, `core/agent/planner.py`, `core/agent/dag_executor.py`): ~400 行新增代码
- **编排器** (`core/agent/orchestrator.py`): 新增 `run_two_speed()`，不改现有 `run_function_calling()` / `run_react()`
- **聊天服务** (`services/chat_service.py`): `_generate_events()` 增加 Router 调用，包装为 `run_two_speed()`
- **提示词** (`prompts/`): 新增 `router.jinja2` + `planner.jinja2` + `dag_executor.jinja2`
- **配置** (`config.py`): 新增 `router_model` 配置（轻量模型），`two_speed_enabled` 开关
- **前端** 无变化（路由行为对用户透明）
