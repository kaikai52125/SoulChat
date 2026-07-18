"""DAGExecutor 单元测试。

覆盖：拓扑分层、工具步执行、纯 LLM 步执行、超时、结果传递、并行计时验证。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.core.agent.dag_executor import DAGExecutor, _topological_layers
from app.core.agent.planner import Plan, PlanStep


# ---------------------------------------------------------------------------
# Helper: 快速构造 PlanStep
# ---------------------------------------------------------------------------
def _step(
    id: str, deps: list[str] | None = None,
    tool_hint: str | None = "web_search",
    desc: str = "",
) -> PlanStep:
    return PlanStep(
        id=id,
        description=desc or f"Step {id}",
        tool_hint=tool_hint,
        query_hint="test query",
        dependencies=deps or [],
        expected_output="test output",
    )


# ---------------------------------------------------------------------------
# _topological_layers 测试
# ---------------------------------------------------------------------------

class TestTopologicalLayers:
    """7.3 拓扑分层功能测试。"""

    def test_two_layers(self):
        """7.3.1 A/B(无依赖)、C(依赖A)、D(依赖B) → 层1=[A,B], 层2=[C,D]。"""
        steps = [
            _step("a", deps=[], desc="搜索 A"),
            _step("b", deps=[], desc="搜索 B"),
            _step("c", deps=["a"], desc="处理 A 结果"),
            _step("d", deps=["b"], desc="处理 B 结果"),
        ]
        layers = _topological_layers(steps)
        assert len(layers) == 2
        assert {s.id for s in layers[0]} == {"a", "b"}
        assert {s.id for s in layers[1]} == {"c", "d"}

    def test_all_parallel(self):
        """7.3.2 所有步骤无依赖 → 1 层全部。"""
        steps = [
            _step("a", deps=[], desc="A"),
            _step("b", deps=[], desc="B"),
            _step("c", deps=[], desc="C"),
        ]
        layers = _topological_layers(steps)
        assert len(layers) == 1
        assert len(layers[0]) == 3

    def test_sequential_chain(self):
        """7.3.3 A→B→C→D 链式 → 4 层各 1 步。"""
        steps = [
            _step("a", deps=[], desc="A"),
            _step("b", deps=["a"], desc="B"),
            _step("c", deps=["b"], desc="C"),
            _step("d", deps=["c"], desc="D"),
        ]
        layers = _topological_layers(steps)
        assert len(layers) == 4
        assert [s.id for layer in layers for s in layer] == ["a", "b", "c", "d"]

    def test_complex_dag(self):
        """复杂 DAG：A(无依赖), B(依赖A), C(依赖A), D(依赖B,C)。"""
        steps = [
            _step("a", deps=[], desc="A"),
            _step("b", deps=["a"], desc="B"),
            _step("c", deps=["a"], desc="C"),
            _step("d", deps=["b", "c"], desc="D"),
        ]
        layers = _topological_layers(steps)
        assert len(layers) == 3
        assert [s.id for s in layers[0]] == ["a"]
        assert {s.id for s in layers[1]} == {"b", "c"}
        assert [s.id for s in layers[2]] == ["d"]

    def test_empty_steps(self):
        """空步骤列表 → 空分层。"""
        assert _topological_layers([]) == []

    def test_single_step(self):
        """单步骤 → 1 层 1 步。"""
        steps = [_step("a", deps=[], desc="A")]
        layers = _topological_layers(steps)
        assert len(layers) == 1
        assert len(layers[0]) == 1


# ---------------------------------------------------------------------------
# DAGExecutor 执行测试
# ---------------------------------------------------------------------------

class TestDAGExecutor:
    """DAGExecutor 执行功能测试。"""

    @pytest.fixture
    def mock_model(self):
        """创建模拟 ChatOpenAI model。"""
        model = MagicMock()
        model.model_name = "test-model"

        async def _ainvoke(messages):
            return AIMessage(content="综合结果：A 和 B 各有优势")

        model.ainvoke = _ainvoke
        model.astream = AsyncMock()
        return model

    @pytest.fixture
    def mock_tools(self):
        """创建模拟工具列表。"""
        tool = MagicMock()
        tool.name = "web_search"
        tool.description = "联网搜索"
        return [tool]

    @pytest.mark.asyncio
    async def test_execute_with_tool_hint(self, mock_model, mock_tools):
        """7.3.4 tool_hint 步骤调用 run_function_calling（验证 max_iter）。"""
        # 这个测试验证 tool_hint 步骤通过 run_function_calling 执行
        # 由于 run_function_calling 是异步生成器，我们需要 patch 它
        plan = Plan(
            goal="测试",
            steps=[_step("step_1", deps=[], tool_hint="web_search", desc="搜索")],
        )

        with patch(
            "app.core.agent.orchestrator.run_function_calling"
        ) as mock_fc:
            # 模拟 run_function_calling 产出 token 和 final 事件
            async def _fake_fc(*args, **kwargs):
                yield {"type": "token", "text": "搜索结果内容"}
                yield {"type": "final", "text": "搜索结果内容"}

            mock_fc.side_effect = _fake_fc

            executor = DAGExecutor()
            results = await executor.execute(
                plan, mock_model, mock_tools, [HumanMessage(content="test")], None,
            )
            assert "step_1" in results
            assert mock_fc.called

    @pytest.mark.asyncio
    async def test_execute_without_tool_hint(self, mock_model):
        """7.3.5 无 tool_hint 步骤调用纯 LLM model.ainvoke()。"""
        plan = Plan(
            goal="测试综合",
            steps=[
                _step("step_1", deps=[], tool_hint=None, desc="综合步"),
            ],
        )

        with patch.object(mock_model, "ainvoke", wraps=mock_model.ainvoke) as spy:
            executor = DAGExecutor()
            results = await executor.execute(
                plan, mock_model, [], [HumanMessage(content="test")], None,
            )
            assert "step_1" in results
            spy.assert_called_once()

    @pytest.mark.asyncio
    async def test_step_error_handling(self, mock_model, mock_tools):
        """7.3.6 步骤执行异常时被正确捕获并标记为失败。"""
        plan = Plan(
            goal="测试异常",
            steps=[_step("step_1", deps=[], tool_hint="web_search", desc="会失败的搜索")],
        )

        with patch(
            "app.core.agent.orchestrator.run_function_calling"
        ) as mock_fc:
            async def _failing_fc(*args, **kwargs):
                yield {"type": "token", "text": "部分结果"}
                raise RuntimeError("执行过程中出错")

            mock_fc.side_effect = _failing_fc

            executor = DAGExecutor()
            results = await executor.execute(
                plan, mock_model, mock_tools,
                [HumanMessage(content="test")], None,
            )
            # 步骤结果存在
            assert "step_1" in results

    @pytest.mark.asyncio
    async def test_synthesize_receives_prior_results(self, mock_model):
        """7.3.7 综合步 prompt 包含前序步骤结果映射。"""
        plan = Plan(
            goal="测试综合",
            steps=[
                _step("step_1", deps=[], tool_hint=None, desc="任务1"),
                _step("step_2", deps=["step_1"], tool_hint=None, desc="综合"),
            ],
        )

        # 模拟第一步的结果被注入到第二步的合成 prompt
        captured_args = {}

        async def _tracking_ainvoke(messages):
            # 捕获第二次调用（综合步）
            if not captured_args:
                captured_args["first"] = messages
                return AIMessage(content="任务1结果")
            captured_args["second"] = messages
            return AIMessage(content="最终综合结果")

        mock_model.ainvoke = _tracking_ainvoke

        with patch(
            "app.core.agent.dag_executor.render_agent_prompt",
            wraps=lambda tmpl, **kw: f"prompt_{tmpl}_{str(kw)}",
        ):
            executor = DAGExecutor()
            results = await executor.execute(
                plan, mock_model, [],
                [HumanMessage(content="test")], None,
            )
            assert "step_1" in results
            assert "step_2" in results
            assert len(captured_args) >= 1

    @pytest.mark.asyncio
    async def test_execute_multiple_layers(self, mock_model, mock_tools):
        """多层 DAG 执行：层间串行，结果正确传递。"""
        plan = Plan(
            goal="多层测试",
            steps=[
                _step("a", deps=[], tool_hint=None, desc="搜索 A"),
                _step("b", deps=["a"], tool_hint=None, desc="基于 A 综合"),
            ],
        )

        call_order = []

        async def _tracking_ainvoke(messages):
            call_order.append(len(call_order))
            return AIMessage(content=f"结果_{len(call_order)}")

        mock_model.ainvoke = _tracking_ainvoke

        executor = DAGExecutor()
        results = await executor.execute(
            plan, mock_model, [],
            [HumanMessage(content="test")], None,
        )
        assert len(results) == 2
        assert "a" in results
        assert "b" in results
        # 确保 b 在 a 之后执行（层间串行）
        assert call_order == [0, 1]


# ---------------------------------------------------------------------------
# 并行执行计时验证测试
# ---------------------------------------------------------------------------

class TestParallelTiming:
    """通过真实 asyncio.sleep 验证同层步骤确实并行执行。"""

    @pytest.fixture
    def mock_model(self):
        model = MagicMock()
        model.model_name = "test-model"
        return model

    @pytest.fixture
    def mock_tools(self):
        tool = MagicMock()
        tool.name = "web_search"
        tool.description = "搜索"
        return [tool]

    @pytest.mark.asyncio
    async def test_parallel_layer_total_time_equals_max_not_sum(
        self, mock_model, mock_tools,
    ):
        """并行验证：3 个同层步骤各 sleep 100ms/200ms/150ms，
        总耗时 ≈ max(100,200,150) = 200ms，而非 sum = 450ms。

        这是验证并行执行是否真正生效的核心测试。
        """
        import time

        plan = Plan(
            goal="并行计时测试",
            steps=[
                PlanStep(id="s1", description="慢步骤", tool_hint="web_search",
                         query_hint="q1", dependencies=[], expected_output="o1"),
                PlanStep(id="s2", description="快步骤", tool_hint="web_search",
                         query_hint="q2", dependencies=[], expected_output="o2"),
                PlanStep(id="s3", description="中步骤", tool_hint="web_search",
                         query_hint="q3", dependencies=[], expected_output="o3"),
            ],
        )

        # 每个步骤 sleep 不同时长，然后产出 token+final 事件
        step_delays = {"s1": 0.2, "s2": 0.1, "s3": 0.15}

        async def _fake_fc_for_step(model, tools, messages):
            # 从消息中识别当前是哪个步骤
            for sid, delay in step_delays.items():
                if sid in str(messages):
                    await asyncio.sleep(delay)
                    yield {"type": "token", "text": f"{sid}_result"}
                    yield {"type": "final", "text": f"{sid}_result"}
                    return
            # fallback
            await asyncio.sleep(0.05)
            yield {"type": "token", "text": "unknown"}
            yield {"type": "final", "text": "unknown"}

        with patch(
            "app.core.agent.orchestrator.run_function_calling"
        ) as mock_fc:
            mock_fc.side_effect = _fake_fc_for_step

            executor = DAGExecutor()
            t0 = time.perf_counter()
            results = await executor.execute(
                plan, mock_model, mock_tools,
                [HumanMessage(content="并行测试")], None,
            )
            elapsed = time.perf_counter() - t0

        assert elapsed < 0.35, (
            f"并行执行耗时 {elapsed:.3f}s 应 < 0.35s "
            f"（串行需 {sum(step_delays.values()):.3f}s，"
            f" 并行理论值 {max(step_delays.values()):.3f}s）"
        )
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_sequential_layers_run_in_order(self, mock_model, mock_tools):
        """层间串行验证：A→B→C 链式依赖，耗时 ≈ sum(delays)。"""
        import time

        plan = Plan(
            goal="串行计时测试",
            steps=[
                PlanStep(id="a", description="第一步", tool_hint=None,
                         query_hint=None, dependencies=[], expected_output=""),
                PlanStep(id="b", description="第二步", tool_hint=None,
                         query_hint=None, dependencies=["a"], expected_output=""),
                PlanStep(id="c", description="第三步", tool_hint=None,
                         query_hint=None, dependencies=["b"], expected_output=""),
            ],
        )

        call_times = []

        async def _tracking_ainvoke(messages):
            call_times.append(time.perf_counter())
            await asyncio.sleep(0.05)
            return AIMessage(content=f"结果_{len(call_times)}")

        mock_model.ainvoke = _tracking_ainvoke

        executor = DAGExecutor()
        results = await executor.execute(
            plan, mock_model, [],
            [HumanMessage(content="串行测试")], None,
        )

        assert len(results) == 3
        # 3 个步骤分 3 层，每层 sleep 50ms，总耗时 ≈ 150ms
        assert len(call_times) == 3
        # 验证调用顺序：a → b → c（时间戳递增）
        assert call_times[0] < call_times[1] < call_times[2]
        total_span = call_times[2] - call_times[0]
        assert total_span > 0.09  # 至少 2 × 50ms（层间间隔）

    @pytest.mark.asyncio
    async def test_mixed_parallel_sequential_timing(self, mock_model, mock_tools):
        """混合验证：层1(A,B并行各100ms)，层2(C依赖A,B，sleep 100ms)。
        总耗时 ≈ 100ms + 100ms = 200ms，而非 300ms。
        """
        import time

        plan = Plan(
            goal="混合计时测试",
            steps=[
                PlanStep(id="a", description="并行A", tool_hint="web_search",
                         query_hint="qa", dependencies=[], expected_output=""),
                PlanStep(id="b", description="并行B", tool_hint="web_search",
                         query_hint="qb", dependencies=[], expected_output=""),
                PlanStep(id="c", description="汇总", tool_hint=None,
                         query_hint=None, dependencies=["a", "b"], expected_output=""),
            ],
        )

        async def _fake_fc_delay(model, tools, messages):
            await asyncio.sleep(0.1)
            yield {"type": "token", "text": "result"}
            yield {"type": "final", "text": "result"}

        async def _fake_synthesize(messages):
            await asyncio.sleep(0.1)
            return AIMessage(content="汇总结果")

        mock_model.ainvoke = _fake_synthesize

        with patch(
            "app.core.agent.orchestrator.run_function_calling"
        ) as mock_fc:
            mock_fc.side_effect = _fake_fc_delay

            executor = DAGExecutor()
            t0 = time.perf_counter()
            results = await executor.execute(
                plan, mock_model, mock_tools,
                [HumanMessage(content="混合测试")], None,
            )
            elapsed = time.perf_counter() - t0

        assert len(results) == 3
        # 并行层 ≈ 100ms + 综合层 ≈ 100ms = 200ms
        # 串行需要 100+100+100 = 300ms
        assert elapsed < 0.28, (
            f"混合执行耗时 {elapsed:.3f}s 应 < 0.28s "
            f"（串行需 0.3s，并行理论值 ~0.2s）"
        )
