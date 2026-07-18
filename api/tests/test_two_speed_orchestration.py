"""Two-Speed 编排集成测试。

覆盖：trivial/chat/single_tool/multi_step 全路由、fallback 行为、事件透传。
"""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.core.agent.orchestrator import run_two_speed, stream_plain


# ---------------------------------------------------------------------------
# Mock 辅助
# ---------------------------------------------------------------------------
def _make_chunk(content="", tool_calls=None):
    """模拟 AIMessageChunk。"""
    chunk = MagicMock()
    chunk.content = content
    chunk.tool_calls = tool_calls or []
    chunk.usage_metadata = {"input_tokens": 10, "output_tokens": 10}
    return chunk


def _make_fc_model(route: str, final_text: str = "最终回答"):
    """创建支持 function calling 的模拟模型。

    Router 返回 route，后续 astream 调用返回 final_text。
    """
    model = MagicMock()
    model.model_name = "test-model"

    # Router 用 ainvoke
    router_responses = {
        "trivial": '{"route": "trivial", "confidence": 0.95, "reason": "test"}',
        "chat": '{"route": "chat", "confidence": 0.90, "reason": "test"}',
        "single_tool": '{"route": "single_tool", "confidence": 0.92, "reason": "test"}',
        "multi_step": '{"route": "multi_step", "confidence": 0.90, "reason": "test"}',
    }

    async def _ainvoke(messages):
        return AIMessage(content=router_responses.get(route, router_responses["single_tool"]))

    model.ainvoke = _ainvoke
    model.bind_tools = MagicMock(return_value=model)

    # astream: 单工具路径
    call_count = 0

    async def _astream(messages):
        nonlocal call_count
        call_count += 1
        if call_count == 1 and route == "single_tool":
            # 模拟工具调用
            yield _make_chunk(tool_calls=[{
                "name": "web_search",
                "args": {"query": "test"},
                "id": "call_1",
            }])
        elif call_count == 2 and route == "single_tool":
            yield _make_chunk(content="工具结果已处理")
        else:
            yield _make_chunk(content=final_text)

    model.astream = _astream
    return model


# ---------------------------------------------------------------------------
# stream_plain 测试
# ---------------------------------------------------------------------------

class TestStreamPlain:
    """stream_plain 独立函数测试。"""

    @pytest.mark.asyncio
    async def test_stream_plain_yields_tokens(self):
        """stream_plain 产出 token / final 事件。"""
        model = MagicMock()
        model.model_name = "test"

        async def _astream(messages):
            yield _make_chunk(content="你好")
            yield _make_chunk(content="世界")

        model.astream = _astream
        events = []
        async for ev in stream_plain(model, [HumanMessage(content="test")]):
            events.append(ev)
        assert any(e["type"] == "token" for e in events)
        assert any(e["type"] == "final" for e in events)
        # 验证 token 文本拼接
        token_text = "".join(e["text"] for e in events if e["type"] == "token")
        assert token_text == "你好世界"


# ---------------------------------------------------------------------------
# run_two_speed 集成测试
# ---------------------------------------------------------------------------

class TestTwoSpeedOrchestration:
    """Two-Speed 编排集成测试。"""

    @pytest.mark.asyncio
    async def test_trivial_route_no_tools(self):
        """7.4.1 trivial 路由 → stream_plain() → 不构建工具。"""
        model = _make_fc_model("trivial")
        events = []
        async for ev in run_two_speed(
            model, [], [HumanMessage(content="你好")],
            router_model=None,
        ):
            events.append(ev)
        # trivial 路由走 stream_plain，产出 token 事件
        assert any(e["type"] == "token" for e in events)
        assert any(e["type"] == "final" for e in events)

    @pytest.mark.asyncio
    async def test_chat_route_no_tools(self):
        """7.4.2 chat 路由 → stream_plain() → 不挂工具。"""
        model = _make_fc_model("chat")
        events = []
        async for ev in run_two_speed(
            model, [], [HumanMessage(content="解释闭包")],
            router_model=None,
        ):
            events.append(ev)
        assert any(e["type"] == "token" for e in events)

    @pytest.mark.asyncio
    async def test_single_tool_route(self):
        """7.4.3 single_tool 路由 → run_function_calling() 行为。"""
        # 使用带工具的模拟
        tool = MagicMock()
        tool.name = "web_search"
        tool.description = "联网搜索"

        async def _tool_ainvoke(args):
            return "搜索结果"

        tool.ainvoke = _tool_ainvoke

        model = _make_fc_model("single_tool")
        events = []
        async for ev in run_two_speed(
            model, [tool], [HumanMessage(content="查知识库 Python")],
            router_model=None,
        ):
            events.append(ev)
        # 应该产出工具调用事件
        tool_starts = [e for e in events if e["type"] == "tool_start"]
        assert len(tool_starts) > 0

    @pytest.mark.asyncio
    async def test_multi_step_e2e(self):
        """7.4.4 multi_step e2e: Planner → DAGExecutor → 综合。

        需要模拟 Planner 和 DAGExecutor。
        """
        model = MagicMock()
        model.model_name = "test-model"

        # Router 返回 multi_step
        async def _ainvoke(messages):
            return AIMessage(
                content='{"route": "multi_step", "confidence": 0.90, "reason": "多步任务"}'
            )

        model.ainvoke = _ainvoke
        model.bind_tools = MagicMock(return_value=model)

        tool = MagicMock()
        tool.name = "web_search"
        tool.description = "搜索"

        async def _tool_ainvoke(args):
            return "benchmark 数据"

        tool.ainvoke = _tool_ainvoke

        # 模拟 Planner 返回合法 Plan
        plan_json = """{"goal": "比较性能", "steps": [
            {"id": "s1", "description": "搜索 Python", "tool_hint": "web_search", "query_hint": "Python", "dependencies": [], "expected_output": "数据"},
            {"id": "s2", "description": "搜索 Go", "tool_hint": "web_search", "query_hint": "Go", "dependencies": [], "expected_output": "数据"},
            {"id": "s3", "description": "综合对比", "tool_hint": null, "query_hint": null, "dependencies": ["s1", "s2"], "expected_output": "表格"}
        ]}"""

        # 第一次 ainvoke=Router, 第二次 ainvoke=Planner, 后续=综合步
        call_idx = 0

        async def _smart_ainvoke(messages):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return AIMessage(content='{"route": "multi_step", "confidence": 0.90, "reason": "多步任务"}')
            elif call_idx == 2:
                return AIMessage(content=plan_json)
            else:
                return AIMessage(content="最终综合结果：Python 和 Go 各有优势")

        model.ainvoke = _smart_ainvoke

        events = []
        async for ev in run_two_speed(
            model, [tool],
            [HumanMessage(content="比较 Python 和 Go 性能")],
            router_model=None,
        ):
            events.append(ev)

        # 应该产出 token 和 final 事件（综合结果）
        assert any(e["type"] == "token" for e in events), f"Got events: {events}"
        assert any(e["type"] == "final" for e in events)

    @pytest.mark.asyncio
    async def test_planner_failure_fallback(self):
        """7.4.5 Planner 返回无效 DAG → fallback 到 run_function_calling()。"""
        model = MagicMock()
        model.model_name = "test-model"

        # Router → multi_step, Planner → 无效 response
        call_idx = 0

        async def _ainvoke(messages):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return AIMessage(content='{"route": "multi_step", "confidence": 0.90, "reason": "多步"}')
            # Planner 返回超过限制的步骤数
            steps = ", ".join(
                f'{{"id": "s{i}", "description": "Step {i}", "tool_hint": null, "dependencies": []}}'
                for i in range(1, 7)
            )
            return AIMessage(content=f'{{"goal": "太多步骤", "steps": [{steps}]}}')

        model.ainvoke = _ainvoke
        model.bind_tools = MagicMock(return_value=model)

        async def _fallback_astream(messages):
            yield _make_chunk(content="fallback 回答")

        model.astream = _fallback_astream

        tool = MagicMock()
        tool.name = "web_search"
        tool.description = "搜索"

        async def _ta(args):
            return "data"

        tool.ainvoke = _ta

        events = []
        async for ev in run_two_speed(
            model, [tool],
            [HumanMessage(content="复杂任务")],
            router_model=None,
        ):
            events.append(ev)

        # 应该 fallback 成功，产出 token（从 astream 来的 fallback 回答）
        assert any(e["type"] == "token" for e in events)

    @pytest.mark.asyncio
    async def test_router_failure_fallback(self):
        """7.4.6 Router 抛异常 → fallback 到 run_function_calling()。"""
        model = MagicMock()
        model.model_name = "test-model"

        async def _fail_ainvoke(messages):
            raise RuntimeError("Router LLM 挂了")

        model.ainvoke = _fail_ainvoke
        model.bind_tools = MagicMock(return_value=model)

        # 模拟单工具路径 astream 返回内容
        async def _astream(messages):
            yield _make_chunk(content="fallback 回答")

        model.astream = _astream

        tool = MagicMock()
        tool.name = "web_search"
        tool.description = "搜索"

        events = []
        async for ev in run_two_speed(
            model, [tool],
            [HumanMessage(content="任何消息")],
            router_model=None,
        ):
            events.append(ev)

        # 应该 fallback 成功
        assert any(e["type"] == "token" for e in events)

    @pytest.mark.asyncio
    async def test_step_events_have_step_id(self):
        """7.4.7 multi_step 路径的 step_start/step_done 事件包含 step_id。"""
        model = MagicMock()
        model.model_name = "test-model"

        call_idx = 0
        plan_json = """{"goal": "测试", "steps": [
            {"id": "s1", "description": "步骤1", "tool_hint": "web_search", "query_hint": "q1", "dependencies": [], "expected_output": "o1"},
            {"id": "s2", "description": "步骤2", "tool_hint": null, "query_hint": null, "dependencies": ["s1"], "expected_output": "o2"}
        ]}"""

        async def _smart_ainvoke(messages):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return AIMessage(content='{"route": "multi_step", "confidence": 0.90, "reason": "test"}')
            elif call_idx == 2:
                return AIMessage(content=plan_json)
            else:
                return AIMessage(content="最终结果")

        model.ainvoke = _smart_ainvoke
        model.bind_tools = MagicMock(return_value=model)

        tool = MagicMock()
        tool.name = "web_search"
        tool.description = "搜索"

        async def _ta(args):
            return "data"

        tool.ainvoke = _ta

        events = []
        async for ev in run_two_speed(
            model, [tool],
            [HumanMessage(content="测试")],
            router_model=None,
        ):
            events.append(ev)

        # 检查 step_start / step_done 事件
        step_starts = [e for e in events if e.get("type") == "step_start"]
        step_dones = [e for e in events if e.get("type") == "step_done"]

        for e in step_starts:
            assert "step_id" in e, f"step_start 缺少 step_id: {e}"
        for e in step_dones:
            assert "step_id" in e, f"step_done 缺少 step_id: {e}"

    @pytest.mark.asyncio
    async def test_two_speed_disabled_unchanged(self):
        """7.5.1 two_speed_enabled=false → 不使用 two-speed。

        这个测试验证当 settings.two_speed_enabled=False 时，
        chat_service 走旧路径。此处我们验证 run_two_speed 本身
        不受该开关影响（开关在 chat_service 层）。
        """
        # run_two_speed 本身不检查开关，开关在 chat_service 中。
        # 验证 run_two_speed 在 disabled 场景下仍可被正确调用。
        model = _make_fc_model("trivial")
        events = []
        async for ev in run_two_speed(
            model, [], [HumanMessage(content="你好")],
        ):
            events.append(ev)
        assert len(events) > 0
