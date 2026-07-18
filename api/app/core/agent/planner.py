"""MicroPlanner: 多步任务规划器，生成 ≤4 步小 DAG 执行计划。

用法:
    planner = MicroPlanner(model)
    plan = await planner.plan("比较 Python 和 Go 的性能，各找 3 个 benchmark", "web_search, knowledge_search")
    # Plan(goal="...", steps=[PlanStep(...), ...])
"""
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.core.agent.prompt_renderer import render_agent_prompt
from app.core.logging import get_logger

logger = get_logger(__name__)


class PlanError(Exception):
    """Planner 验证失败时抛出的异常。调用方应 fallback 到 run_function_calling()。"""
    pass


class PlanStep(BaseModel):
    """DAG 中的单个执行步骤。"""
    id: str
    description: str
    tool_hint: str | None = None
    query_hint: str | None = None
    dependencies: list[str] = []
    expected_output: str = ""


class Plan(BaseModel):
    """DAG 执行计划。"""
    goal: str
    steps: list[PlanStep]


MAX_PLAN_STEPS = 4
MAX_PLAN_DEPTH = 2


def _compute_depth(step_id: str, steps_map: dict[str, PlanStep], depth_cache: dict[str, int]) -> int:
    """递归计算步骤在依赖链中的深度。

    深度定义：从根步骤（无依赖）到当前步骤的最长依赖链长度。
    根深度为 0，每层依赖 +1。
    """
    if step_id in depth_cache:
        return depth_cache[step_id]
    step = steps_map[step_id]
    if not step.dependencies:
        depth_cache[step_id] = 0
        return 0
    max_dep_depth = max(
        _compute_depth(dep, steps_map, depth_cache) for dep in step.dependencies
    )
    depth = max_dep_depth + 1
    depth_cache[step_id] = depth
    return depth


def _detect_cycle(steps: list[PlanStep]) -> bool:
    """检测 DAG 是否有循环依赖（DFS 拓扑排序检测）。"""
    adj: dict[str, list[str]] = {s.id: list(s.dependencies) for s in steps}
    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node: str) -> bool:
        if node in visited:
            return False
        if node in visiting:
            return True  # 发现环
        if node not in adj:
            return False
        visiting.add(node)
        for dep in adj[node]:
            if dfs(dep):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    for s in steps:
        if s.id not in visited:
            if dfs(s.id):
                return True
    return False


def validate_plan(plan: Plan) -> Plan:
    """验证 Plan 合法性。

    检查点：
    - 步骤数 ≤ 4
    - 深度 ≤ 2
    - 无循环依赖
    - dependencies 引用的 id 都存在于 steps 中

    Raises:
        PlanError: 任一检查失败时抛出。
    """
    steps = plan.steps
    # 1. 步骤数上限
    if len(steps) > MAX_PLAN_STEPS:
        raise PlanError(f"步骤数超过 {MAX_PLAN_STEPS}，当前 {len(steps)}")

    # 2. 所有 step id 唯一
    ids = [s.id for s in steps]
    if len(set(ids)) != len(ids):
        raise PlanError("步骤 id 不唯一")

    # 3. dependencies 引用检查
    all_ids = set(ids)
    for s in steps:
        for dep in s.dependencies:
            if dep not in all_ids:
                raise PlanError(f"步骤 {s.id} 依赖了不存在的步骤 {dep}")

    # 4. 循环依赖检测
    if _detect_cycle(steps):
        raise PlanError("存在循环依赖")

    # 5. 深度上限
    steps_map = {s.id: s for s in steps}
    depth_cache: dict[str, int] = {}
    for s in steps:
        d = _compute_depth(s.id, steps_map, depth_cache)
        if d > MAX_PLAN_DEPTH:
            raise PlanError(f"深度超过 {MAX_PLAN_DEPTH}，步骤 {s.id} 深度为 {d}")

    return plan


class MicroPlanner:
    """多步任务 DAG 规划器。

    根据用户消息 + 可用工具列表，生成 ≤4 步、深度 ≤2 的小 DAG。
    """

    def __init__(self, model: ChatOpenAI):
        self._model = model

    async def plan(self, message: str, tools_summary: str) -> Plan:
        """生成 DAG 执行计划。

        Args:
            message: 用户消息。
            tools_summary: 可用工具摘要字符串。

        Returns:
            验证通过的 Plan 对象。

        Raises:
            PlanError: 生成的计划验证不通过时抛出。调用方应 fallback。
        """
        prompt = render_agent_prompt(
            "planner.jinja2",
            message=message,
            tools_summary=tools_summary,
        )
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content="请生成 JSON 格式的 DAG 计划。"),
        ]
        try:
            resp = await self._model.ainvoke(messages)
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            parsed = self._extract_json(text)
            plan = self._parse_plan(parsed)
            return validate_plan(plan)
        except PlanError:
            raise
        except Exception as e:
            raise PlanError(f"Planner 生成失败: {e}") from e

    def _parse_plan(self, data: dict[str, Any]) -> Plan:
        """把 JSON dict 解析为 Plan 对象。"""
        goal = str(data.get("goal", ""))
        raw_steps: list[dict] = data.get("steps", [])
        if not raw_steps:
            raise PlanError("Planner 未生成任何步骤")
        steps = [PlanStep(**s) for s in raw_steps]
        return Plan(goal=goal, steps=steps)

    @staticmethod
    def _extract_json(text: str) -> dict:
        """从 LLM 输出中提取 JSON 对象。"""
        text = text.strip()
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass
        import re as _re
        m = _re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, _re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except (json.JSONDecodeError, ValueError):
                pass
        m = _re.search(r"\{.*\}", text, _re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except (json.JSONDecodeError, ValueError):
                pass
        raise PlanError(f"无法从 Planner 输出中提取 JSON: {text[:200]}")


__all__ = ["MicroPlanner", "Plan", "PlanStep", "PlanError", "validate_plan"]
