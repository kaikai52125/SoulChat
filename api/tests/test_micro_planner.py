"""MicroPlanner 单元测试。

覆盖：步骤上限、深度上限、循环检测、缺失依赖、合法计划、并行依赖。
"""
import pytest
from langchain_core.messages import AIMessage
from unittest.mock import MagicMock

from app.core.agent.planner import (
    MAX_PLAN_STEPS,
    MicroPlanner,
    Plan,
    PlanError,
    PlanStep,
    validate_plan,
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _make_planner_model(json_response: str) -> MagicMock:
    """创建一个模拟的 ChatOpenAI model。"""
    model = MagicMock()
    model.model_name = "test-planner-model"

    async def _ainvoke(messages):
        return AIMessage(content=json_response)

    model.ainvoke = _ainvoke
    return model


# ---------------------------------------------------------------------------
# validate_plan 测试
# ---------------------------------------------------------------------------

class TestValidatePlan:
    """验证器功能测试。"""

    def test_step_limit(self):
        """7.2.1 6 步 → 验证器抛 PlanError。"""
        steps = [
            PlanStep(id=f"step_{i}", description=f"Step {i}", dependencies=[])
            for i in range(1, MAX_PLAN_STEPS + 2)  # 5 步，超过 4
        ]
        plan = Plan(goal="测试", steps=steps)
        with pytest.raises(PlanError, match="步骤数超过"):
            validate_plan(plan)

    def test_depth_limit(self):
        """7.2.2 深度 3 → 验证器抛 PlanError。

        构造 A→B→C→D 链，深度 = 3（A=0,B=1,C=2,D=3），超过 2。
        """
        steps = [
            PlanStep(id="step_a", description="A", dependencies=[]),
            PlanStep(id="step_b", description="B", dependencies=["step_a"]),
            PlanStep(id="step_c", description="C", dependencies=["step_b"]),
            PlanStep(id="step_d", description="D", dependencies=["step_c"]),
        ]
        plan = Plan(goal="测试链式", steps=steps)
        with pytest.raises(PlanError, match="深度超过"):
            validate_plan(plan)

    def test_cycle_detection(self):
        """7.2.3 A→B→A 循环依赖 → 验证器抛 PlanError。"""
        steps = [
            PlanStep(id="step_a", description="A", dependencies=["step_b"]),
            PlanStep(id="step_b", description="B", dependencies=["step_a"]),
            PlanStep(id="step_c", description="C", dependencies=[]),
        ]
        plan = Plan(goal="测试循环", steps=steps)
        with pytest.raises(PlanError, match="循环依赖"):
            validate_plan(plan)

    def test_missing_dependency(self):
        """7.2.4 dependencies 引用了不存在的 step_id → PlanError。"""
        steps = [
            PlanStep(id="step_a", description="A", dependencies=[]),
            PlanStep(id="step_b", description="B", dependencies=["step_nonexistent"]),
        ]
        plan = Plan(goal="测试缺失依赖", steps=steps)
        with pytest.raises(PlanError, match="不存在"):
            validate_plan(plan)

    def test_valid_plan_passes(self):
        """7.2.5 合法 ≤4 步 ≤2 层无环 DAG 通过验证。"""
        steps = [
            PlanStep(id="step_1", description="搜索 A", dependencies=[]),
            PlanStep(id="step_2", description="搜索 B", dependencies=[]),
            PlanStep(
                id="step_3", description="综合",
                dependencies=["step_1", "step_2"],
            ),
        ]
        plan = Plan(goal="比较 A 和 B", steps=steps)
        validated = validate_plan(plan)
        assert validated.goal == "比较 A 和 B"
        assert len(validated.steps) == 3

    def test_empty_dependency_parallel(self):
        """7.2.6 所有步骤 dependencies=[] → 全部在同一层并行。"""
        steps = [
            PlanStep(id="step_1", description="任务1", dependencies=[]),
            PlanStep(id="step_2", description="任务2", dependencies=[]),
            PlanStep(id="step_3", description="任务3", dependencies=[]),
        ]
        plan = Plan(goal="并行任务", steps=steps)
        validated = validate_plan(plan)
        assert len(validated.steps) == 3
        # 所有步骤无依赖 → 深度均为 0（≤2）
        from app.core.agent.planner import _compute_depth
        steps_map = {s.id: s for s in validated.steps}
        cache: dict = {}
        for s in validated.steps:
            d = _compute_depth(s.id, steps_map, cache)
            assert d == 0

    def test_duplicate_id(self):
        """重复 step id 应报错。"""
        steps = [
            PlanStep(id="step_1", description="A", dependencies=[]),
            PlanStep(id="step_1", description="B", dependencies=[]),
        ]
        plan = Plan(goal="重复", steps=steps)
        with pytest.raises(PlanError, match="不唯一"):
            validate_plan(plan)


class TestMicroPlanner:
    """MicroPlanner 集成测试（Mock LLM）。"""

    @pytest.mark.asyncio
    async def test_plan_success(self):
        """正常规划返回合法 Plan。"""
        model = _make_planner_model("""
        {
            "goal": "比较 Python 和 Go 的性能",
            "steps": [
                {"id": "step_1", "description": "搜索 Python benchmark", "tool_hint": "web_search", "query_hint": "Python benchmark", "dependencies": [], "expected_output": "数据"},
                {"id": "step_2", "description": "搜索 Go benchmark", "tool_hint": "web_search", "query_hint": "Go benchmark", "dependencies": [], "expected_output": "数据"},
                {"id": "step_3", "description": "综合比较", "tool_hint": null, "query_hint": null, "dependencies": ["step_1", "step_2"], "expected_output": "对比表格"}
            ]
        }
        """)
        planner = MicroPlanner(model)
        plan = await planner.plan("比较 Python 和 Go", "web_search")
        assert plan.goal == "比较 Python 和 Go 的性能"
        assert len(plan.steps) == 3
        assert plan.steps[2].dependencies == ["step_1", "step_2"]

    @pytest.mark.asyncio
    async def test_plan_error_propagation(self):
        """Planner LLM 抛异常 → PlanError。"""
        model = MagicMock()
        model.model_name = "test"

        async def _fail(_m):
            raise RuntimeError("LLM 挂了")

        model.ainvoke = _fail
        planner = MicroPlanner(model)
        with pytest.raises(PlanError):
            await planner.plan("测试", "")

    @pytest.mark.asyncio
    async def test_plan_validation_on_generated(self):
        """Planner 生成超过限制的步骤 → PlanError。"""
        # 6 步超出限制
        steps_json = ", ".join(
            f'{{"id": "step_{i}", "description": "Step {i}", "tool_hint": null, "dependencies": []}}'
            for i in range(1, 7)
        )
        model = _make_planner_model('{"goal": "太多步骤", "steps": [' + steps_json + ']}')
        planner = MicroPlanner(model)
        with pytest.raises(PlanError):
            await planner.plan("测试", "")
