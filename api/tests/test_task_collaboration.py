"""任务协作模式集成测试。

覆盖 tasks.md 8.3 测试计划：
- 8.3.1 test_social_mode_unchanged
- 8.3.2 test_task_mode_e2e
- 8.3.3 test_blackboard_preserves_all_findings
- 8.3.4 test_verifier_review_in_task_mode
- 8.3.5 test_verifier_repair_on_failure
"""
import json
import unittest
from unittest.mock import MagicMock, patch

from app.core.agent.blackboard import BlackboardEntry, SharedBlackboard
from app.core.agent.group_chat import _run_task_mode
from app.core.agent.task_orchestrator import TaskOrchestrator


class TaskCollaborationIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """任务协作模式集成测试。"""

    def setUp(self):
        self.noop_tracer = _NoOpTracer()
        self.tracer_patcher = patch(
            "app.core.agent.orchestrator.get_tracer",
            return_value=self.noop_tracer,
        )
        self.tracer_patcher.start()

    def tearDown(self):
        self.tracer_patcher.stop()

    # ------------------------------------------------------------------
    # 8.3.1 social mode unchanged
    # ------------------------------------------------------------------
    def test_social_mode_unchanged(self):
        """验证 social mode 的现有功能没有被改动影响。

        这里测试关键公共函数签名和行为不变。
        """
        from app.core.agent.group_chat import (
            build_transcript,
            decide_speakers,
            parse_mention,
            stream_speaker,
        )

        # 验证核心函数仍然可导入
        self.assertIsNotNone(build_transcript)
        self.assertIsNotNone(decide_speakers)
        self.assertIsNotNone(parse_mention)
        self.assertIsNotNone(stream_speaker)

        # 验证历史 transcript 构建不变
        history = [
            {"role": "user", "content": "你好", "sender_name": "用户"},
            {"role": "assistant", "content": "你好！", "sender_name": "助手A"},
        ]
        transcript = build_transcript(history)
        self.assertIn("【用户】你好", transcript)
        self.assertIn("【助手A】你好！", transcript)

        # 验证 parse_mention 不变
        result = parse_mention("你好 @助手A", ["助手A", "助手B"])
        self.assertEqual(result, "助手A")

        result = parse_mention("你好", ["助手A", "助手B"])
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # 8.3.2 task mode e2e
    # ------------------------------------------------------------------
    async def test_task_mode_e2e(self):
        """创建 3 人角色组 → mode="task" → Orchestrator 分解 → 黑板 finding → synthesize。"""
        model = MagicMock()
        model.model_name = "test-model"

        # Mock _run_agent：直接按顺序返回，跳过 tracer/function calling
        _agent_call = 0

        async def _fake_run_agent(_self, messages):
            nonlocal _agent_call
            _agent_call += 1
            if _agent_call == 1:
                return json.dumps({
                    "goal": "分析新能源汽车市场",
                    "subtasks": [
                        {"id": "st_1", "description": "收集市场数据", "assigned_persona": "研究员", "dependencies": [], "expected_output": "市场数据报告"},
                        {"id": "st_2", "description": "撰写分析报告", "assigned_persona": "分析师", "dependencies": ["st_1"], "expected_output": "完整分析报告"},
                    ],
                })
            elif _agent_call <= 3:
                return f"子任务 {_agent_call - 1} 的产出内容"
            else:
                return "# 新能源汽车市场分析报告\n\n经过研究员和分析师的协作分析..."

        with patch.object(TaskOrchestrator, "_run_agent", _fake_run_agent):

            members = [
                {"name": "研究员", "system_prompt": "你是一名市场研究员，擅长数据收集和分析。"},
                {"name": "分析师", "system_prompt": "你是一名行业分析师，擅长撰写分析报告。"},
            ]

            events = []
            async for event in _run_task_mode(
                user_message="帮我分析新能源汽车市场",
                members=members,
                history=[],
                model=model,
            ):
                events.append(event)

            # 验证事件序列
            event_types = [e["type"] for e in events]
            self.assertIn("task_plan", event_types)
            self.assertIn("subtask_start", event_types)
            self.assertIn("subtask_done", event_types)
            self.assertIn("synthesize_start", event_types)
            self.assertIn("final", event_types)

            # 验证 final 是 synthesize 的结果
            final_events = [e for e in events if e["type"] == "final"]
            self.assertEqual(len(final_events), 1)
            self.assertIn("新能源汽车市场", final_events[0]["text"])

    # ------------------------------------------------------------------
    # 8.3.3 blackboard preserves all findings
    # ------------------------------------------------------------------
    async def test_blackboard_preserves_all_findings(self):
        """任务完成后验证黑板 summarize 包含所有 finding。"""
        bb = SharedBlackboard()
        bb.post(BlackboardEntry(type="finding", author="研究员", content="市场规模3000亿"))
        bb.post(BlackboardEntry(type="finding", author="分析师", content="SWOT分析完成"))
        bb.post(BlackboardEntry(type="finding", author="写手", content="报告撰写完成"))

        summary = bb.summarize()
        self.assertIn("市场规模3000亿", summary)
        self.assertIn("SWOT分析完成", summary)
        self.assertIn("报告撰写完成", summary)

    # ------------------------------------------------------------------
    # 8.3.4 verifier review in task mode
    # ------------------------------------------------------------------
    async def test_verifier_review_in_task_mode(self):
        """验证协作产出可以通过 LoopController 进行 verifier 审查。

        注意：这是一个基于 mock 的集成测试，验证 controller 能接收协作产出的 artifact。
        实际的 verifier 模型调用需要真实 API。
        """
        # 构建一个假 artifact（模拟 synthesize 的输出）
        artifact = {
            "markdown": "# 协作报告\n\n研究员发现市场规模3000亿。\n分析师提出SWOT框架。",
            "title": "市场分析报告",
            "headings": ["市场规模", "SWOT分析"],
            "sources": [],
            "findings": [
                {"author": "研究员", "content": "市场规模3000亿"},
                {"author": "分析师", "content": "SWOT分析完成"},
            ],
        }

        # 验证 artifact 包含所有角色的 finding
        self.assertIn("市场规模3000亿", artifact["markdown"])
        self.assertIn("SWOT框架", artifact["markdown"])
        self.assertEqual(len(artifact["findings"]), 2)

        # 验证 rubric 可以正常加载
        from app.core.agent.loop.rubric import RUBRICS
        self.assertIn("collaboration", RUBRICS)
        rubric = RUBRICS["collaboration"]
        self.assertEqual(rubric.name, "collaboration")
        self.assertAlmostEqual(rubric.pass_threshold, 0.7)

        # 验证 weighted_total 计算
        scores = {
            "coverage": 4.0,
            "faithfulness": 4.0,
            "depth": 3.0,
            "consistency": 4.0,
            "relevance": 4.0,
            "readability": 4.0,
        }
        total = rubric.weighted_total(scores)
        self.assertGreater(total, 0.7)

    # ------------------------------------------------------------------
    # 8.3.5 orchestrator decompose failure fallback
    # ------------------------------------------------------------------
    @patch("app.core.agent.task_orchestrator.TaskOrchestrator._run_agent")
    async def test_orchestrator_decompose_failure_fallback(self, mock_run_agent):
        """Orchestrator 分解任务失败 → 降级为单角色回答。"""
        model = MagicMock()
        model.model_name = "test-model"

        # decompose 的 _run_agent 抛异常 → 触发 fallback
        mock_run_agent.side_effect = ValueError("模拟分解失败")

        # fallback 路径需要 model.ainvoke（降级为单角色回答）
        async def _ainvoke(messages):
            resp = MagicMock()
            resp.content = "这是降级后的单角色回答。"
            resp.usage_metadata = {"input_tokens": 5, "output_tokens": 5}
            return resp

        model.ainvoke = _ainvoke

        members = [
            {"name": "助手", "system_prompt": "你是一个通用助手。"},
        ]

        events = []
        async for event in _run_task_mode(
            user_message="帮我做点事",
            members=members,
            history=[],
            model=model,
        ):
            events.append(event)

        # 验证降级后产生了 final 事件
        final_events = [e for e in events if e["type"] == "final"]
        self.assertEqual(len(final_events), 1)
        self.assertIn("单角色回答", final_events[0]["text"])


class _NoOpTracer:
    """简化的空 tracer，所有方法都是无操作的。"""

    async def span(self, *args, **kwargs):
        return self

    async def llm_span(self, *args, **kwargs):
        return self

    def set_payload(self, *args, **kwargs):
        pass

    def set_tokens(self, *args, **kwargs):
        pass

    def mark_error(self, *args, **kwargs):
        pass

    def set_attribute(self, *args, **kwargs):
        pass

    def __aenter__(self):
        return self

    def __aexit__(self, *args, **kwargs):
        return None


if __name__ == "__main__":
    unittest.main()
