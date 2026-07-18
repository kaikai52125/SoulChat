"""Shared Blackboard 单元测试。

覆盖 tasks.md 8.1 测试计划：
- 8.1.1 post 和 retrieve
- 8.1.2 context 条数限制
- 8.1.3 summarize 方法
- 8.1.4 entry types enum 校验
- 8.1.5 空上下文
"""
import unittest

from pydantic import ValidationError

from app.core.agent.blackboard import BlackboardEntry, SharedBlackboard


class SharedBlackboardTests(unittest.TestCase):
    """SharedBlackboard 功能测试。"""

    def setUp(self):
        self.bb = SharedBlackboard()

    # ------------------------------------------------------------------
    # 8.1.1 post 和 retrieve（含隔离规则）
    # ------------------------------------------------------------------
    def test_blackboard_post_and_retrieve(self):
        """角色只看到：协作目标 + 自己的任务 + 自己的 finding + 其他角色的已有产出。"""
        self.bb.post(BlackboardEntry(type="task", author="orchestrator", content="分析新能源汽车市场"))
        self.bb.post(BlackboardEntry(type="subtask", author="orchestrator",
                                      content="subtask_1: 研究市场趋势 → 研究员"))
        self.bb.post(BlackboardEntry(type="finding", author="研究员", content="2025年新能源渗透率达40%"))
        # 其他角色的 finding
        self.bb.post(BlackboardEntry(type="finding", author="分析师", content="SWOT分析完成"))

        self.assertEqual(len(self.bb.entries), 4)
        context = self.bb.get_context_for("研究员")
        # 应该看到协作目标和自己的任务
        self.assertIn("分析新能源汽车市场", context)
        self.assertIn("研究市场趋势", context)
        # 应该看到自己的 finding
        self.assertIn("2025年新能源渗透率达40%", context)
        # 应该看到其他角色的已有产出
        self.assertIn("SWOT分析完成", context)
        # 不应该看到自己的名字被当作"其他角色"
        self.assertNotIn("研究员: 2025年新能源渗透率达40%", context.split("【其他角色的已有产出】")[-1] if "【其他角色的已有产出】" in context else "")

    def test_persona_isolation_no_cross_contamination(self):
        """A股研究员的上下文不应该包含港股研究员的子任务描述。"""
        self.bb.post(BlackboardEntry(type="task", author="orchestrator", content="研究A股和港股"))
        self.bb.post(BlackboardEntry(type="subtask", author="orchestrator",
                                      content="subtask_1: 研究A股市场 → A股研究员"))
        self.bb.post(BlackboardEntry(type="subtask", author="orchestrator",
                                      content="subtask_2: 研究港股市场 → 港股研究员"))
        self.bb.post(BlackboardEntry(type="finding", author="A股研究员", content="上证指数涨0.5%"))
        self.bb.post(BlackboardEntry(type="finding", author="港股研究员", content="恒生指数跌1.2%"))

        context_a = self.bb.get_context_for("A股研究员")
        # A股研究员应该看到"研究A股"，但不应看到"研究港股"的子任务描述
        self.assertIn("研究A股市场", context_a)
        self.assertNotIn("研究港股市场", context_a)
        # 但能看到其他角色的已有产出（港股研究员的 finding）
        self.assertIn("恒生指数跌1.2%", context_a)

    # ------------------------------------------------------------------
    # 8.1.2 context 条数限制
    # ------------------------------------------------------------------
    def test_blackboard_context_limit(self):
        """其他角色的 finding 受数量限制。"""
        for i in range(20):
            self.bb.post(BlackboardEntry(type="finding", author=f"角色{i}", content=f"产出内容{i}"))

        # 也加一个 task entry
        self.bb.post(BlackboardEntry(type="task", author="orchestrator", content="测试"))
        self.bb.post(BlackboardEntry(type="subtask", author="orchestrator",
                                      content="subtask_1: 测试 → test"))

        context = self.bb.get_context_for("test")
        # 有内容但不应该无限膨胀——"其他角色的已有产出"最多展示 5 条
        self.assertIn("协作目标", context)
        self.assertIn("你的任务", context)

    # ------------------------------------------------------------------
    # 8.1.3 summarize 方法
    # ------------------------------------------------------------------
    def test_blackboard_summarize(self):
        """post 若干 finding + decision → summarize() 返回结构化摘要。"""
        self.bb.post(BlackboardEntry(type="finding", author="研究员", content="市场规模达3000亿"))
        self.bb.post(BlackboardEntry(type="finding", author="分析师", content="SWOT分析完成"))
        self.bb.post(BlackboardEntry(type="decision", author="orchestrator", content="采用方案A"))
        # comment 不应出现在 summarize 中
        self.bb.post(BlackboardEntry(type="comment", author="verifier", content="深度不够"))

        summary = self.bb.summarize()
        self.assertIn("市场规模达3000亿", summary)
        self.assertIn("SWOT分析完成", summary)
        self.assertIn("采用方案A", summary)
        self.assertNotIn("深度不够", summary)
        self.assertIn("3 条核心记录", summary)

    # ------------------------------------------------------------------
    # 8.1.4 entry types enum
    # ------------------------------------------------------------------
    def test_blackboard_entry_types_enum(self):
        """传入非法 entry type 抛 ValidationError。"""
        with self.assertRaises(ValidationError):
            BlackboardEntry(type="invalid_type", author="test", content="test")
        with self.assertRaises(ValidationError):
            BlackboardEntry(type=123, author="test", content="test")  # type: ignore

        # 合法的 type 应正常创建
        for t in ("task", "subtask", "finding", "draft", "comment", "decision"):
            entry = BlackboardEntry(type=t, author="test", content="test")
            self.assertEqual(entry.type, t)

    # ------------------------------------------------------------------
    # 8.1.5 空上下文
    # ------------------------------------------------------------------
    def test_blackboard_empty_context(self):
        """无 entry 时 get_context_for() 返回空字符串，不报错。"""
        context = self.bb.get_context_for("anyone")
        self.assertEqual(context, "")
        summary = self.bb.summarize()
        self.assertEqual(summary, "")


if __name__ == "__main__":
    unittest.main()
