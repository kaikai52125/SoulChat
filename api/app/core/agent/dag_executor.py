"""DAGExecutor: 按 DAG 拓扑执行计划节点，同层并行、层间串行。

用法:
    executor = DAGExecutor()
    results = await executor.execute(plan, model, tools, messages, persona)
    # {"step_1": "结果文本", "step_2": "结果文本", ...}
"""
import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.agent.prompt_renderer import render_agent_prompt
from app.core.agent.tracing import get_tracer
from app.core.agent.planner import Plan, PlanStep
from app.core.logging import get_logger

logger = get_logger(__name__)

# 每层执行超时（秒）
_LAYER_TIMEOUT = 60.0


def _topological_layers(steps: list[PlanStep]) -> list[list[PlanStep]]:
    """BFS 拓扑排序：返回按执行顺序分层的步骤列表。

    第 0 层：无依赖的步骤（可并行执行）。
    第 N 层：依赖全部在第 N-1 层或之前已满足的步骤。
    """
    steps_map = {s.id: s for s in steps}
    remaining = set(s.id for s in steps)
    completed: set[str] = set()
    layers: list[list[PlanStep]] = []

    while remaining:
        # 当前层：所有依赖都已满足的步骤
        ready = [
            steps_map[sid]
            for sid in remaining
            if all(dep in completed for dep in steps_map[sid].dependencies)
        ]
        if not ready:
            # 理论上不应该发生（validate_plan 已检查无环），但兜底处理
            logger.warning("拓扑排序卡住：剩余步骤 %s 无法满足依赖", remaining)
            break
        layers.append(ready)
        for s in ready:
            remaining.discard(s.id)
            completed.add(s.id)

    return layers


class DAGExecutor:
    """DAG 执行器：按拓扑分层并行执行 DAG 节点。

    每层内所有节点用 asyncio.gather 并行执行，层间串行等待。
    有 tool_hint 的步骤运行独立 function calling 循环，无 tool_hint 的步骤走纯 LLM 综合。
    """

    def __init__(self, layer_timeout: float = _LAYER_TIMEOUT):
        self._layer_timeout = layer_timeout

    async def execute(
        self,
        plan: Plan,
        model: ChatOpenAI,
        tools: list,
        messages: list,
        persona: Any = None,
    ) -> dict[str, str]:
        """执行 DAG 计划，返回 {step_id: result_text} 映射。

        Args:
            plan: MicroPlanner 生成的 Plan 对象。
            model: ChatOpenAI 实例。
            tools: LangChain StructuredTool 列表。
            messages: 当前对话的 LangChain 消息列表。
            persona: 角色配置对象（用于获取 temperature 等）。

        Returns:
            {step_id: result_text} 字典。执行失败的步骤结果为错误描述字符串。
        """
        layers = _topological_layers(plan.steps)
        results: dict[str, str] = {}
        # 先 yield 所有 plan 信息（用于 tracing）
        tracer = get_tracer()
        async with tracer.span("dag_executor", span_type="planner") as tsp:
            tsp.set_payload("step_count", len(plan.steps))
            tsp.set_payload("layer_count", len(layers))

            total_timeout = len(layers) * self._layer_timeout
            try:
                async with asyncio.timeout(total_timeout):
                    for layer_idx, layer in enumerate(layers):
                        await self._execute_layer(
                            layer, layer_idx, plan, model, tools, messages,
                            persona, results,
                        )
            except asyncio.TimeoutError:
                logger.error(
                    "DAG 执行超时（%ds）: plan=%s 已完成步骤=%d",
                    total_timeout, plan.goal[:80], len(results),
                )
                # 超时后，所有未完成步骤标为超时
                for s in plan.steps:
                    if s.id not in results:
                        results[s.id] = "执行超时"

        return results

    async def _execute_layer(
        self,
        layer: list[PlanStep],
        layer_idx: int,
        plan: Plan,
        model: ChatOpenAI,
        tools: list,
        messages: list,
        persona: Any,
        results: dict[str, str],
    ) -> None:
        """并行执行层内所有步骤。"""
        logger.info(
            "DAG 执行层 %d/%d: %d 个步骤",
            layer_idx + 1, len(_topological_layers(plan.steps)),
            len(layer),
        )
        coros = [
            self._execute_step(
                step, plan, model, tools, messages, persona, results,
            )
            for step in layer
        ]
        step_results = await asyncio.gather(*coros, return_exceptions=True)

        for step, result in zip(layer, step_results, strict=False):
            if isinstance(result, Exception):
                results[step.id] = f"执行失败: {result}"
                logger.warning("DAG 步骤 %s 执行失败: %s", step.id, result)
            else:
                results[step.id] = result

    async def _execute_step(
        self,
        step: PlanStep,
        plan: Plan,
        model: ChatOpenAI,
        tools: list,
        messages: list,
        persona: Any,
        prior_results: dict[str, str],
    ) -> str:
        """执行单个 DAG 步骤。

        有 tool_hint → 注入步骤描述作为 system 前缀，运行 function calling 循环。
        无 tool_hint → 纯 LLM 合成（不挂工具），基于前序步骤结果生成回答。
        """
        if step.tool_hint:
            return await self._execute_tool_step(step, model, tools, messages)
        else:
            return await self._execute_synthesis_step(step, plan, prior_results, model)

    async def _execute_tool_step(
        self,
        step: PlanStep,
        model: ChatOpenAI,
        tools: list,
        messages: list,
    ) -> str:
        """执行有 tool_hint 的步骤：注入步骤描述 + 运行 function calling。

        从 run_function_calling 的事件流中收集最终文本。
        使用懒加载避免与 orchestrator.py 的循环导入。
        """
        from app.core.agent.orchestrator import run_function_calling

        # 注入步骤描述作为临时 system 消息
        step_context = (
            f"【当前步骤】{step.description}\n"
            f"{'查询提示: ' + step.query_hint if step.query_hint else ''}"
        )
        step_messages = [
            SystemMessage(content=step_context),
            *messages,
        ]

        collected_text = ""
        async for ev in run_function_calling(model, tools, step_messages):
            ev_type = ev.get("type")
            if ev_type == "token":
                collected_text += ev.get("text", "")
            elif ev_type == "final":
                collected_text += ev.get("text", "")
        return collected_text or "（步骤执行完成，未生成文本）"

    async def _execute_synthesis_step(
        self,
        step: PlanStep,
        plan: Plan,
        prior_results: dict[str, str],
        model: ChatOpenAI,
    ) -> str:
        """执行无 tool_hint 的综合步骤：纯 LLM 基于前序结果生成。

        使用 dag_synthesize.jinja2 模板构建 prompt，调用 model.ainvoke。
        """
        # 从前序结果中取本步骤依赖的结果
        step_descriptions = {s.id: s.description for s in plan.steps}
        relevant_results: dict[str, str] = {}
        for dep_id in step.dependencies:
            if dep_id in prior_results:
                relevant_results[dep_id] = prior_results[dep_id]
        # 如果没有显式依赖，用所有前序结果
        if not relevant_results:
            relevant_results = dict(prior_results)

        synthesize_prompt = render_agent_prompt(
            "dag_synthesize.jinja2",
            goal=plan.goal,
            step_results=relevant_results,
            step_descriptions=step_descriptions,
        )
        messages = [HumanMessage(content=synthesize_prompt)]
        resp = await model.ainvoke(messages)
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        return text


async def run_dag_with_events(
    executor: DAGExecutor,
    plan: Plan,
    model: ChatOpenAI,
    tools: list,
    messages: list,
    persona: Any = None,
) -> AsyncGenerator[dict, None]:
    """执行 DAG 并产出带 step_id 的事件流。

    事件类型：
    - {"type": "step_start", "step_id": str, "description": str, "tool_hint": str|None}
    - {"type": "step_done", "step_id": str, "status": "ok"|"error"}
    - {"type": "tool_start", "tool": str, "query": str, "step_id": str}
    - {"type": "tool_result", "tool": str, "query": str, "status": str, "text": str, "step_id": str}

    先 yield 所有 step_start 事件，再并行执行，最后 yield step_done。
    """
    # 先 yield step_start 事件
    for step in plan.steps:
        yield {
            "type": "step_start",
            "step_id": step.id,
            "description": step.description,
            "tool_hint": step.tool_hint,
        }

    layers = _topological_layers(plan.steps)
    results: dict[str, str] = {}

    for layer in layers:
        async def _run_one(step: PlanStep) -> tuple[str, str, bool]:
            """执行一个步骤，返回 (step_id, result, ok)。"""
            try:
                # 检查步骤类型
                if step.tool_hint:
                    result = await executor._execute_tool_step(
                        step, model, tools, messages,
                    )
                else:
                    result = await executor._execute_synthesis_step(
                        step, plan, results, model,
                    )
                return step.id, result, True
            except Exception as e:
                return step.id, f"执行失败: {e}", False

        coros = [_run_one(s) for s in layer]
        # 并行执行层内步骤
        step_outcomes = await asyncio.gather(*coros, return_exceptions=True)

        for outcome in step_outcomes:
            if isinstance(outcome, Exception):
                continue
            step_id, result, ok = outcome
            results[step_id] = result
            yield {
                "type": "step_done",
                "step_id": step_id,
                "status": "ok" if ok else "error",
            }


__all__ = [
    "DAGExecutor", "_topological_layers", "run_dag_with_events",
]
