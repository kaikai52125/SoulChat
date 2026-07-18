"""Task Orchestrator 单元测试。

覆盖 tasks.md 8.2 测试计划：
- 8.2.1 decompose 生成有效计划
- 8.2.2 decompose 尊重成员能力
- 8.2.3 decompose 单成员兜底
- 8.2.4 execute 并行无依赖子任务
- 8.2.5 execute 串行有依赖子任务
- 8.2.6 execute 单子任务失败
"""
import json
import unittest
from unittest.mock import MagicMock

from app.core.agent.blackboard import SharedBlackboard
from app.core.agent.task_orchestrator import (
    Subtask,
    TaskOrchestrator,
    TaskPlan,
)


def _make_mock_model(responses: list | None = None, tools_enabled: bool = False):
    """创建模拟的 ChatOpenAI model，支持 function calling 路径。

    Args:
        responses: 依次返回的响应内容列表
        tools_enabled: True 时 model.bind_tools 返回带 astream 的 mock
    """
    model = MagicMock()
    model.model_name = "test-model"
    call_count = 0

    async def _ainvoke(messages):
        nonlocal call_count
        if responses and call_count < len(responses):
            text = responses[call_count]
        else:
            text = '{"goal": "测试任务", "subtasks": [{"id": "st_1", "description": "测试", "assigned_persona": "研究员", "dependencies": [], "expected_output": "报告"}]}'
        call_count += 1
        resp = MagicMock()
        resp.content = text
        resp.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
        return resp

    # 支持 bind_tools → astream（run_function_calling 需要）
    mock_with_tools = MagicMock()
    mock_with_tools.model_name = "test-model-with-tools"

    _astream_count = 0
    async def _astream(messages):
        nonlocal _astream_count
        _astream_count += 1
        chunk = MagicMock()
        if responses and _astream_count <= len(responses):
            chunk.content = responses[_astream_count - 1]
        else:
            chunk.content = '{"goal": "测试", "subtasks": [{"id": "s1", "description": "t", "assigned_persona": "研究员", "dependencies": [], "expected_output": "r"}]}'
        chunk.tool_calls = []
        chunk.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
        yield chunk

    mock_with_tools.astream = _astream
    model.bind_tools = MagicMock(return_value=mock_with_tools)
    model.ainvoke = _ainvoke
    model.astream = _astream
    return model


class TaskOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    """TaskOrchestrator 功能测试。"""

    # ------------------------------------------------------------------
    # 8.2.1 decompose 生成有效计划
    # ------------------------------------------------------------------
    async def test_decompose_generates_valid_plan(self):
        """输入"分析新能源汽车市场" + 3 个成员能力 → 返回 TaskPlan(subtasks ≥ 1)。"""
        model = _make_mock_model([
            json.dumps({
                "goal": "分析新能源汽车市场现状与趋势",
                "subtasks": [
                    {
                        "id": "st_1",
                        "description": "市场规模与增长数据",
                        "assigned_persona": "数据分析师",
                        "dependencies": [],
                        "expected_output": "市场数据报告",
                    },
                    {
                        "id": "st_2",
                        "description": "竞争格局分析",
                        "assigned_persona": "行业分析师",
                        "dependencies": [],
                        "expected_output": "竞争格局报告",
                    },
                ],
            })
        ])
        orchestrator = TaskOrchestrator(model)
        capabilities = [
            {"name": "数据分析师", "brief": "擅长数据分析和市场研究"},
            {"name": "行业分析师", "brief": "擅长行业分析和竞争研究"},
            {"name": "报告撰写者", "brief": "擅长撰写报告"},
        ]

        plan = await orchestrator.decompose("分析新能源汽车市场", capabilities)

        self.assertIsInstance(plan, TaskPlan)
        self.assertEqual(len(plan.subtasks), 2)
        for st in plan.subtasks:
            self.assertIsInstance(st, Subtask)
            self.assertTrue(st.assigned_persona in [c["name"] for c in capabilities])

    # ------------------------------------------------------------------
    # 8.2.2 decompose 尊重成员能力
    # ------------------------------------------------------------------
    async def test_decompose_respects_member_capabilities(self):
        """成员能力含"数据分析" → 分析类 subtask 指派给该成员。"""
        model = _make_mock_model([
            json.dumps({
                "goal": "市场调研",
                "subtasks": [
                    {
                        "id": "st_1",
                        "description": "数据分析部分",
                        "assigned_persona": "数据分析师",
                        "dependencies": [],
                        "expected_output": "数据报告",
                    },
                ],
            })
        ])
        orchestrator = TaskOrchestrator(model)
        capabilities = [
            {"name": "数据分析师", "brief": "擅长数据分析和市场研究，精通Excel和SQL"},
            {"name": "内容写手", "brief": "擅长写文章和报告，文笔好"},
        ]

        plan = await orchestrator.decompose("做一份市场调研报告", capabilities)
        # "数据分析部分"应指派给"数据分析师"
        data_task = [s for s in plan.subtasks if "数据分析" in s.description]
        if data_task:
            self.assertEqual(data_task[0].assigned_persona, "数据分析师")

    # ------------------------------------------------------------------
    # 8.2.3 decompose 单成员兜底
    # ------------------------------------------------------------------
    async def test_decompose_single_member_fallback(self):
        """只有 1 个成员时，所有 subtask 指派给该成员。"""
        model = _make_mock_model([
            json.dumps({
                "goal": "写一份市场报告",
                "subtasks": [
                    {
                        "id": "st_1",
                        "description": "收集市场数据",
                        "assigned_persona": "全能助手",
                        "dependencies": [],
                        "expected_output": "市场数据",
                    },
                    {
                        "id": "st_2",
                        "description": "撰写报告",
                        "assigned_persona": "全能助手",
                        "dependencies": ["st_1"],
                        "expected_output": "完整报告",
                    },
                ],
            })
        ])
        orchestrator = TaskOrchestrator(model)
        capabilities = [{"name": "全能助手", "brief": "可以帮助完成各种任务"}]

        plan = await orchestrator.decompose("写一份报告", capabilities)
        self.assertEqual(len(plan.subtasks), 2)
        for st in plan.subtasks:
            self.assertEqual(st.assigned_persona, "全能助手")

    # ------------------------------------------------------------------
    # 8.2.4 execute 并行无依赖子任务
    # ------------------------------------------------------------------
    async def test_execute_parallel_independent_subtasks(self):
        """3 个无依赖的 subtask → 并行执行。"""
        model = _make_mock_model()
        orchestrator = TaskOrchestrator(model)
        bb = SharedBlackboard()

        plan = TaskPlan(
            goal="测试并行",
            subtasks=[
                Subtask(id="a", description="任务A", assigned_persona="研究员1", dependencies=[]),
                Subtask(id="b", description="任务B", assigned_persona="研究员2", dependencies=[]),
                Subtask(id="c", description="任务C", assigned_persona="研究员3", dependencies=[]),
            ],
        )
        members = [
            {"name": "研究员1", "system_prompt": "你是一个研究员。"},
            {"name": "研究员2", "system_prompt": "你是一个研究员。"},
            {"name": "研究员3", "system_prompt": "你是一个研究员。"},
        ]

        results = {}
        async for ev in orchestrator.execute_stream(plan, bb, members):
            results[ev["subtask_id"]] = ev.get("status", "ok")

        self.assertEqual(len(results), 3)
        self.assertIn("a", results)
        self.assertIn("b", results)
        self.assertIn("c", results)

    # ------------------------------------------------------------------
    # 8.2.5 execute 串行有依赖子任务
    # ------------------------------------------------------------------
    async def test_execute_sequential_dependent_subtasks(self):
        """A→B→C 链式依赖 → 分 3 层串行执行。"""
        model = _make_mock_model()
        orchestrator = TaskOrchestrator(model)
        bb = SharedBlackboard()

        plan = TaskPlan(
            goal="测试串行",
            subtasks=[
                Subtask(id="a", description="任务A", assigned_persona="研究员1", dependencies=[]),
                Subtask(id="b", description="任务B", assigned_persona="研究员2", dependencies=["a"]),
                Subtask(id="c", description="任务C", assigned_persona="研究员3", dependencies=["b"]),
            ],
        )
        members = [
            {"name": "研究员1", "system_prompt": "你是一个研究员。"},
            {"name": "研究员2", "system_prompt": "你是一个研究员。"},
            {"name": "研究员3", "system_prompt": "你是一个研究员。"},
        ]

        # 验证拓扑分层：应有 3 层，每层 1 个
        layers = TaskOrchestrator._topological_layers(plan.subtasks)
        self.assertEqual(len(layers), 3)

        results = {}
        async for ev in orchestrator.execute_stream(plan, bb, members):
            results[ev["subtask_id"]] = ev.get("status", "ok")
        self.assertEqual(len(results), 3)

    # ------------------------------------------------------------------
    # 8.2.6 execute 单子任务失败
    # ------------------------------------------------------------------
    async def test_execute_one_subtask_failure(self):
        """一个 subtask 执行失败 → 其他 subtask 正常完成。"""
        call_count = 0

        async def _ainvoke_with_failure(messages):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("模型调用失败")
            resp = MagicMock()
            resp.content = "正常完成"
            resp.usage_metadata = {"input_tokens": 5, "output_tokens": 5}
            return resp

        model = MagicMock()
        model.model_name = "test-model"
        model.ainvoke = _ainvoke_with_failure

        orchestrator = TaskOrchestrator(model)
        bb = SharedBlackboard()

        plan = TaskPlan(
            goal="测试失败",
            subtasks=[
                Subtask(id="a", description="任务A", assigned_persona="研究员1", dependencies=[]),
                Subtask(id="b", description="任务B", assigned_persona="研究员2", dependencies=[]),
            ],
        )
        members = [
            {"name": "研究员1", "system_prompt": "你是一个研究员。"},
            {"name": "研究员2", "system_prompt": "你是一个研究员。"},
        ]

        results = {}
        async for ev in orchestrator.execute_stream(plan, bb, members):
            results[ev["subtask_id"]] = ev.get("status", "ok")

        self.assertEqual(len(results), 2)
        self.assertIn("a", results)
        self.assertIn("b", results)
        # 检查黑板的 entry
        findings = bb.get_by_type("finding")
        self.assertEqual(len(findings), 2)


if __name__ == "__main__":
    unittest.main()
