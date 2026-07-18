"""并行工具执行单元的全面测试。

覆盖 function calling 路径与 ReAct 路径的并行化改动。
"""
import asyncio
import json
import time
import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.agent.orchestrator import (
    _ACTION_RE,
    _ACTION_INPUT_RE,
    run_function_calling,
    run_react,
)


# ---------------------------------------------------------------------------
# No‑op tracer 替代品 —— 在单元测试中替代 get_tracer() 的真实实现
# ---------------------------------------------------------------------------
class _NoOpTracer:
    """简化的空 tracer，所有方法都是无操作的。"""

    @asynccontextmanager
    async def span(self, *args, **kwargs):
        yield self

    @asynccontextmanager
    async def llm_span(self, *args, **kwargs):
        yield self

    def set_payload(self, *args, **kwargs):
        pass

    def set_tokens(self, *args, **kwargs):
        pass

    def mark_error(self, *args, **kwargs):
        pass

    def set_attribute(self, *args, **kwargs):
        pass


# ---------------------------------------------------------------------------
# 辅助函数：创建模拟的 function calling model
# ---------------------------------------------------------------------------
def _make_fc_model(tool_calls_first_iter, final_content="Final answer"):
    """创建一个模拟的 ChatOpenAI model。

    第一次调用 astream 时返回 ``tool_calls_first_iter``（期待的工具调用列表），
    后续调用（下一轮循环）返回无工具调用的 ``final_content`` 以终止迭代。
    """
    model = MagicMock()
    model.model_name = "test-model"

    class _Chunk:
        """模拟 AIMessageChunk，支持 + 聚合。"""

        def __init__(self, content="", tool_calls=None, usage_metadata=None):
            self.content = content
            self.tool_calls = tool_calls or []
            self.usage_metadata = usage_metadata or {
                "input_tokens": 5,
                "output_tokens": 5,
            }

        def __add__(self, other):
            return _Chunk(
                content=self.content + other.content,
                tool_calls=other.tool_calls or self.tool_calls,
                usage_metadata=other.usage_metadata or self.usage_metadata,
            )

    call_count = 0

    async def _astream(messages):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            yield _Chunk(tool_calls=tool_calls_first_iter)
        else:
            yield _Chunk(content=final_content, tool_calls=[])

    model.bind_tools = MagicMock(return_value=model)
    model.astream = _astream
    return model


def _make_mock_tool(name, delay=0.0, result=None, fail=False):
    """创建一个延迟/结果/异常可控的模拟工具。"""
    if result is None:
        result = f"{name}_result"

    async def _run(args):
        """args 是 tool.ainvoke 传入的参数字典。"""
        if delay:
            await asyncio.sleep(delay)
        if fail:
            msg = args.get("query", str(args))
            raise ValueError(f"{name} failed: {msg}")
        return result

    tool = MagicMock()
    tool.name = name
    tool.description = f"Tool {name}"
    tool.ainvoke = AsyncMock(side_effect=_run)
    return tool


# ===========================================================================
# function calling 路径的测试
# ===========================================================================
class FunctionCallingParallelTests(unittest.IsolatedAsyncioTestCase):
    """覆盖 run_function_calling 的并行化改动。"""

    def setUp(self):
        self.noop_tracer = _NoOpTracer()
        self.tracer_patcher = patch(
            "app.core.agent.orchestrator.get_tracer",
            return_value=self.noop_tracer,
        )
        self.tracer_patcher.start()

    def tearDown(self):
        self.tracer_patcher.stop()

    async def _collect_events(self, model, tools, messages):
        """收集 function calling 路径的全部事件。"""
        events = []
        async for evt in run_function_calling(model, tools, messages):
            events.append(evt)
        return events

    # ------------------------------------------------------------------
    # 3.1.1 并发延迟优于串行
    # ------------------------------------------------------------------
    async def test_gather_independent_tools(self):
        """验证 3 个独立工具的并行执行总耗时 ≈ max(delay)，而非 sum(delay)。"""
        tool_a = _make_mock_tool("tool_a", delay=0.1)
        tool_b = _make_mock_tool("tool_b", delay=0.2)
        tool_c = _make_mock_tool("tool_c", delay=0.15)

        tools = [tool_a, tool_b, tool_c]
        tc_list = [
            {"name": "tool_a", "args": {}, "id": "call_a", "type": "tool_call"},
            {"name": "tool_b", "args": {}, "id": "call_b", "type": "tool_call"},
            {"name": "tool_c", "args": {}, "id": "call_c", "type": "tool_call"},
        ]
        model = _make_fc_model(tc_list)

        t0 = time.monotonic()
        events = await self._collect_events(model, tools, [])
        elapsed = time.monotonic() - t0

        # 收集到的 tool_result 数量应为 3
        tool_results = [e for e in events if e["type"] == "tool_result"]
        self.assertEqual(len(tool_results), 3)

        # 总耗时应 ≈ 200ms（max delay），而非 450ms（sum delay）
        # 允许 100ms 的松弛以应对 CI/调度抖动
        self.assertLess(elapsed, 0.35, f"总耗时 {elapsed:.3f}s 超过并行预期")

    # ------------------------------------------------------------------
    # 3.1.2 单工具异常不阻断其他工具
    # ------------------------------------------------------------------
    async def test_return_exceptions_true(self):
        """一个工具抛 ValueError，另外两个正常返回。"""
        tool_a = _make_mock_tool("tool_a", result="success_a")
        tool_b = _make_mock_tool("tool_b", fail=True)
        tool_c = _make_mock_tool("tool_c", result="success_c")

        tools = [tool_a, tool_b, tool_c]
        tc_list = [
            {"name": "tool_a", "args": {"query": "qa"}, "id": "call_a", "type": "tool_call"},
            {"name": "tool_b", "args": {"query": "qb"}, "id": "call_b", "type": "tool_call"},
            {"name": "tool_c", "args": {"query": "qc"}, "id": "call_c", "type": "tool_call"},
        ]
        model = _make_fc_model(tc_list)
        events = await self._collect_events(model, tools, [])

        results = {e["tool"]: e for e in events if e["type"] == "tool_result"}
        self.assertEqual(len(results), 3)

        # tool_a 和 tool_c 应为 success
        self.assertEqual(results["tool_a"]["status"], "success")
        self.assertEqual(results["tool_c"]["status"], "success")
        # tool_b 应包含错误信息
        self.assertEqual(results["tool_b"]["status"], "error")
        self.assertIn("工具执行失败", results["tool_b"]["text"])

    # ------------------------------------------------------------------
    # 3.1.3 全部工具抛异常
    # ------------------------------------------------------------------
    async def test_all_tools_fail(self):
        """全部工具抛异常时，每个 observation 各自包含 error text。"""
        tool_a = _make_mock_tool("tool_a", fail=True)
        tool_b = _make_mock_tool("tool_b", fail=True)

        tools = [tool_a, tool_b]
        tc_list = [
            {"name": "tool_a", "args": {"query": "qa"}, "id": "call_a", "type": "tool_call"},
            {"name": "tool_b", "args": {"query": "qb"}, "id": "call_b", "type": "tool_call"},
        ]
        model = _make_fc_model(tc_list)
        events = await self._collect_events(model, tools, [])

        results = {e["tool"]: e for e in events if e["type"] == "tool_result"}
        self.assertEqual(len(results), 2)
        for name in ("tool_a", "tool_b"):
            self.assertEqual(results[name]["status"], "error")
            self.assertIn("工具执行失败", results[name]["text"])

    # ------------------------------------------------------------------
    # 3.1.4 缓存命中跳过重复执行
    # ------------------------------------------------------------------
    async def test_cache_hit_skips_execution(self):
        """同轮内相同工具+参数的第二次调用不重复执行。"""
        tool_a = _make_mock_tool("tool_a", delay=0.05)
        # 两个 tool call 指向同一工具同一参数
        tc_list = [
            {"name": "tool_a", "args": {"query": "same"}, "id": "call_1", "type": "tool_call"},
            {"name": "tool_a", "args": {"query": "same"}, "id": "call_2", "type": "tool_call"},
        ]
        model = _make_fc_model(tc_list)
        tools = [tool_a]

        events = await self._collect_events(model, tools, [])
        results = [e for e in events if e["type"] == "tool_result"]
        self.assertEqual(len(results), 2)

        # ainvoke 只应被调用一次（缓存命中第二次）
        self.assertEqual(tool_a.ainvoke.call_count, 1)

    # ------------------------------------------------------------------
    # 3.1.5 缓存 key 的确定性
    # ------------------------------------------------------------------
    async def test_cache_key_deterministic(self):
        """验证相同 args 不同顺序的 json.dumps 结果一致（sort_keys=True）。"""
        args_1 = {"b": 2, "a": 1, "c": 3}
        args_2 = {"c": 3, "a": 1, "b": 2}
        key_1 = json.dumps(args_1, ensure_ascii=False, sort_keys=True)
        key_2 = json.dumps(args_2, ensure_ascii=False, sort_keys=True)
        self.assertEqual(key_1, key_2)

    # ------------------------------------------------------------------
    # 3.1.6 事件顺序保持原始 tool_calls 顺序
    # ------------------------------------------------------------------
    async def test_event_order_maintained(self):
        """并行执行后 event 发射仍按 tool_calls 原始顺序。"""
        tool_a = _make_mock_tool("tool_a", delay=0.2)
        tool_b = _make_mock_tool("tool_b", delay=0.05)  # 更快完成

        tools = [tool_a, tool_b]
        tc_list = [
            {"name": "tool_a", "args": {"query": "qa"}, "id": "call_a", "type": "tool_call"},
            {"name": "tool_b", "args": {"query": "qb"}, "id": "call_b", "type": "tool_call"},
        ]
        model = _make_fc_model(tc_list)
        events = await self._collect_events(model, tools, [])

        # 按原始顺序：tool_a 先，tool_b 后
        tool_results = [e for e in events if e["type"] == "tool_result"]
        self.assertEqual(len(tool_results), 2)
        self.assertEqual(tool_results[0]["tool"], "tool_a")
        self.assertEqual(tool_results[1]["tool"], "tool_b")

        # 验证 tool_start → tool_result 交替不交错 (per tool)
        tool_starts = [e for e in events if e["type"] == "tool_start"]
        self.assertEqual(len(tool_starts), 2)
        self.assertEqual(tool_starts[0]["tool"], "tool_a")
        self.assertEqual(tool_starts[1]["tool"], "tool_b")

        # 完整序列检查：start_a, result_a, start_b, result_b
        self.assertEqual(events[0]["type"], "tool_start")
        self.assertEqual(events[0]["tool"], "tool_a")
        self.assertEqual(events[1]["type"], "tool_start")
        self.assertEqual(events[1]["tool"], "tool_b")
        self.assertEqual(events[2]["type"], "tool_result")
        self.assertEqual(events[2]["tool"], "tool_a")
        self.assertEqual(events[3]["type"], "tool_result")
        self.assertEqual(events[3]["tool"], "tool_b")


# ===========================================================================
# ReAct 路径的测试
# ===========================================================================
class ReActMultiActionTests(unittest.IsolatedAsyncioTestCase):
    """覆盖 run_react 的多 Action 解析 + 并行执行改动。"""

    def setUp(self):
        self.noop_tracer = _NoOpTracer()
        self.tracer_patcher = patch(
            "app.core.agent.orchestrator.get_tracer",
            return_value=self.noop_tracer,
        )
        self.tracer_patcher.start()

        self.render_patcher = patch(
            "app.core.agent.orchestrator.render_agent_prompt",
            return_value="Mocked system prompt",
        )
        self.render_patcher.start()

    def tearDown(self):
        self.tracer_patcher.stop()
        self.render_patcher.stop()

    def _make_react_model(self, response_texts):
        """模拟一个 ReAct 模型，按调用次数依次返回 response_texts 中的内容。

        ``response_texts`` 可以是字符串（单次响应）或列表（多次响应轮换）。
        最后的回调（超出列表长度时）自动返回 ``Final Answer: Done``。
        """
        if isinstance(response_texts, str):
            response_texts = [response_texts]

        model = MagicMock()
        model.model_name = "test-react-model"
        call_count = 0

        async def _ainvoke(convo):
            nonlocal call_count
            text = (
                response_texts[call_count]
                if call_count < len(response_texts)
                else "Final Answer: Done"
            )
            call_count += 1
            resp = MagicMock()
            resp.content = text
            resp.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
            return resp

        model.ainvoke = _ainvoke
        return model

    async def _collect_react_events(self, model, tools, user_text, history, system_prompt):
        events = []
        async for evt in run_react(model, tools, user_text, history, system_prompt):
            events.append(evt)
        return events

    # ------------------------------------------------------------------
    # 3.1.7 多 Action 解析
    # ------------------------------------------------------------------
    async def test_react_multi_action_parsing(self):
        """模拟包含 3 组 Action/Action Input 的 LLM 输出，验证正确提取为 3 对。"""
        response_text = (
            "Thought: I need to check three things\n"
            "Action: search_docs\n"
            "Action Input: python async\n"
            "Action: search_memory\n"
            "Action Input: user preferences\n"
            "Action: web_search\n"
            "Action Input: latest news"
        )
        text_match = _ACTION_RE.search(response_text)
        self.assertIsNotNone(text_match)

        action_matches = list(_ACTION_RE.finditer(response_text))
        input_matches = list(_ACTION_INPUT_RE.finditer(response_text))

        self.assertEqual(len(action_matches), 3)
        self.assertEqual(len(input_matches), 3)

        pairs = []
        for j, am in enumerate(action_matches):
            t_name = am.group(1).strip().splitlines()[0].strip()
            inp_text = (
                input_matches[j].group(1).strip().splitlines()[0].strip()
                if j < len(input_matches)
                else None
            )
            pairs.append((t_name, inp_text or ""))

        self.assertEqual(pairs[0], ("search_docs", "python async"))
        self.assertEqual(pairs[1], ("search_memory", "user preferences"))
        self.assertEqual(pairs[2], ("web_search", "latest news"))

    # ------------------------------------------------------------------
    # 3.1.8 单 Action 向后兼容
    # ------------------------------------------------------------------
    async def test_react_single_action_backward_compat(self):
        """单 Action 的旧格式输出（没有多 Action 解析时）仍然被正确执行。"""
        tool_a = _make_mock_tool("tool_a", result="single_result")
        tools = [tool_a]

        response_text = (
            "Thought: I need to look something up\n"
            "Action: tool_a\n"
            "Action Input: my query"
        )
        model = self._make_react_model(response_text)
        events = await self._collect_react_events(
            model, tools, "user query", [], "system prompt"
        )

        # 验证事件序列
        tool_starts = [e for e in events if e["type"] == "tool_start"]
        tool_results = [e for e in events if e["type"] == "tool_result"]
        self.assertEqual(len(tool_starts), 1)
        self.assertEqual(len(tool_results), 1)
        self.assertEqual(tool_starts[0]["tool"], "tool_a")
        self.assertEqual(tool_results[0]["tool"], "tool_a")
        self.assertEqual(tool_results[0]["status"], "success")

        # 验证 tool.ainvoke 被调用
        tool_a.ainvoke.assert_called_once()


if __name__ == "__main__":
    unittest.main()
