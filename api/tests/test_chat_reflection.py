"""ChatReflector 单元测试。

测试覆盖：
- ChatReflector.reflect() JSON 解析与 should_remember 逻辑
- _format_reflection_block() Markdown 格式
- _is_trivial_message() 寒暄检测
- _should_skip_reflection() 短回答跳过
- _extract_recent_reflections() 反思块提取
"""
import json
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from app.core.agent.reflector import (
    ChatReflector,
    ReflectionResult,
    _extract_recent_reflections,
    _format_reflection_block,
    _is_trivial_message,
    _should_skip_reflection,
    _summarize_user_msg,
)


class TestReflectorResults(unittest.TestCase):
    """ChatReflector.reflect() 返回合法 ReflectionResult。"""

    def setUp(self):
        self.reflector = ChatReflector()

    async def _mock_reflect(self, json_response: str, user_msg="Python 和 Go 性能对比", answer="Python 和 Go 各有优劣…"):
        """辅助：用 mock LLM 调用 reflect。"""
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=MagicMock(
            content=json_response,
        ))
        return await self.reflector.reflect(
            user_msg=user_msg,
            assistant_answer=answer,
            tool_calls_log=[{"tool": "knowledge_search", "query": "Python Go 性能", "status": "success"}],
            persona_name="测试助手",
            model_override=mock_model,
        )

    def test_reflector_returns_valid_json(self):
        """6.1.1 给定典型输入，返回合法 ReflectionResult。"""
        json_resp = json.dumps({
            "completeness": "涵盖了主要方面",
            "tool_usage": "使用了 knowledge_search",
            "user_satisfaction": "回答了用户问题",
            "key_takeaway": "性能对比需覆盖 CPU、内存、并发、生态",
            "should_remember": True,
        }, ensure_ascii=False)
        result = asyncio_run(self._mock_reflect(json_resp))
        self.assertIsInstance(result, ReflectionResult)
        self.assertTrue(result.completeness)
        self.assertTrue(result.tool_usage)
        self.assertTrue(result.user_satisfaction)
        self.assertTrue(result.key_takeaway)
        self.assertTrue(result.should_remember)

    def test_reflector_should_remember_true(self):
        """6.1.2 回答有明显遗漏时 should_remember=true。"""
        json_resp = json.dumps({
            "completeness": "遗漏了内存管理差异",
            "tool_usage": "可补充 web_search 获取最新 benchmark",
            "user_satisfaction": "部分命中意图",
            "key_takeaway": "性能对比需覆盖 CPU、内存、并发、生态",
            "should_remember": True,
        }, ensure_ascii=False)
        result = asyncio_run(self._mock_reflect(json_resp))
        self.assertTrue(result.should_remember)
        self.assertIn("内存", result.key_takeaway)

    def test_reflector_should_remember_false(self):
        """6.1.3 回答完整正确时 should_remember=false。"""
        json_resp = json.dumps({
            "completeness": "完整覆盖了所有问题点",
            "tool_usage": "工具使用合理",
            "user_satisfaction": "完全命中用户意图",
            "key_takeaway": "本次回答无问题",
            "should_remember": False,
        }, ensure_ascii=False)
        result = asyncio_run(self._mock_reflect(json_resp))
        self.assertFalse(result.should_remember)
        self.assertEqual(result.key_takeaway, "本次回答无问题")

    def test_reflector_returns_empty_on_json_parse_failure(self):
        """LLM 返回无法解析的内容时返回空 ReflectionResult。"""
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=MagicMock(
            content="这不是 JSON",
        ))
        result = asyncio_run(self.reflector.reflect(
            user_msg="测试",
            assistant_answer="测试回答",
            tool_calls_log=[],
            persona_name="测试助手",
            model_override=mock_model,
        ))
        self.assertIsInstance(result, ReflectionResult)
        self.assertFalse(result.should_remember)

    def test_reflector_handles_llm_exception(self):
        """LLM 调用抛出异常时返回空 ReflectionResult，不传播异常。"""
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(side_effect=Exception("API 错误"))
        result = asyncio_run(self.reflector.reflect(
            user_msg="测试",
            assistant_answer="测试回答",
            tool_calls_log=[],
            persona_name="测试助手",
            model_override=mock_model,
        ))
        self.assertIsInstance(result, ReflectionResult)
        self.assertFalse(result.should_remember)
        self.assertEqual(result.completeness, "")


class TestReflectionBlockFormat(unittest.TestCase):
    """_format_reflection_block() 格式验证。"""

    def test_reflection_block_format(self):
        """6.1.4 输出符合 Markdown `--- reflection 时间戳 ---` 格式。"""
        result = ReflectionResult(
            completeness="涵盖了主要方面",
            tool_usage="使用了 knowledge_search",
            user_satisfaction="回答了用户问题",
            key_takeaway="性能对比需覆盖多维度",
            should_remember=True,
        )
        block = _format_reflection_block(result, "Python 和 Go 性能对比")
        lines = block.strip().split("\n")

        # 第一行：--- reflection 时间戳 ---
        self.assertTrue(lines[0].startswith("--- reflection "))
        self.assertTrue(lines[0].endswith(" ---"))

        # 包含对话摘要
        self.assertIn("**对话**: Python 和 Go 性能对比", lines[1])

        # 包含三维评估
        self.assertIn("**完整性**", block)
        self.assertIn("**工具利用**", block)
        self.assertIn("**用户满意度**", block)
        self.assertIn("**经验**", block)

        # 最后一行：---
        self.assertEqual(lines[-1].strip(), "---")

        # 时间戳格式验证（只要紧跟在 "--- reflection " 后 ISO 格式即可）
        ts_part = lines[0][len("--- reflection "):-len(" ---")]
        # 尝试解析为日期
        try:
            datetime.fromisoformat(ts_part)
        except ValueError:
            self.fail(f"时间戳格式不正确: {ts_part}")

    def test_reflection_block_without_remember(self):
        """should_remember=false 时仍正常格式化。"""
        result = ReflectionResult(
            completeness="完整",
            tool_usage="合理",
            user_satisfaction="满意",
            key_takeaway="本次回答无问题",
            should_remember=False,
        )
        block = _format_reflection_block(result, "你好")
        self.assertIn("**经验**: 本次回答无问题", block)


class TestTrivialMessageDetection(unittest.TestCase):
    """_is_trivial_message() 寒暄检测。"""

    def test_detects_greetings(self):
        """6.1.5 常见寒暄返回 true。"""
        self.assertTrue(_is_trivial_message("你好"))
        self.assertTrue(_is_trivial_message("你好啊"))
        self.assertTrue(_is_trivial_message("您好"))
        self.assertTrue(_is_trivial_message("谢谢"))
        self.assertTrue(_is_trivial_message("多谢"))
        self.assertTrue(_is_trivial_message("Hi"))
        self.assertTrue(_is_trivial_message("hello"))
        self.assertTrue(_is_trivial_message("嗨"))
        self.assertTrue(_is_trivial_message("嗯嗯"))
        self.assertTrue(_is_trivial_message("好的"))
        self.assertTrue(_is_trivial_message("ok"))
        self.assertTrue(_is_trivial_message("在吗"))

    def test_non_trivial_messages(self):
        """非寒暄消息返回 false。"""
        self.assertFalse(_is_trivial_message("帮我写个 Python 脚本"))
        self.assertFalse(_is_trivial_message("今天天气怎么样"))
        self.assertFalse(_is_trivial_message("Python 和 Go 哪个性能好"))
        self.assertFalse(_is_trivial_message("讲个故事"))
        self.assertFalse(_is_trivial_message("什么是量子计算"))

    def test_empty_or_short(self):
        """空消息或长度 ≤2 返回 true。"""
        self.assertTrue(_is_trivial_message(""))
        self.assertTrue(_is_trivial_message("  "))
        self.assertTrue(_is_trivial_message("哦"))
        self.assertTrue(_is_trivial_message("嗯"))
        self.assertTrue(_is_trivial_message("啊"))

    def test_greeting_with_punctuation(self):
        """带标点的寒暄仍然匹配。"""
        self.assertTrue(_is_trivial_message("你好！"))
        self.assertTrue(_is_trivial_message("谢谢。"))
        self.assertTrue(_is_trivial_message("好的~"))


class TestShouldSkipReflection(unittest.TestCase):
    """_should_skip_reflection() 跳过判断。"""

    def test_short_answer_no_tools_skips(self):
        """6.1.6 回答 < 50 字且未使用工具时返回 true。"""
        self.assertTrue(_should_skip_reflection("好的，我知道了。", []))
        self.assertTrue(_should_skip_reflection("没问题", []))
        self.assertTrue(_should_skip_reflection("你好啊，有什么可以帮你的吗", []))

    def test_long_answer_no_tools_does_not_skip(self):
        """回答 >= 50 字即使无工具也不跳过。"""
        long = "这是一个超过五十个字的回答。我需要在这里写很多内容来确保它足够长，以便触发反思。好的，现在应该够了。"
        self.assertGreaterEqual(len(long), 50)
        self.assertFalse(_should_skip_reflection(long, []))

    def test_short_answer_with_tools_does_not_skip(self):
        """回答很短但用了工具也不跳过。"""
        self.assertFalse(_should_skip_reflection("找到了", [{"tool": "knowledge_search", "query": "test"}]))

    def test_empty_answer_skips(self):
        """空回答跳过。"""
        self.assertTrue(_should_skip_reflection("", []))
        self.assertTrue(_should_skip_reflection("   ", []))


class TestExtractRecentReflections(unittest.TestCase):
    """_extract_recent_reflections() 提取最近 N 条反思。"""

    def _make_memory_text(self, count: int) -> str:
        """生成 count 条反思块的 memory_text。"""
        blocks = []
        for i in range(count):
            blocks.append(
                f"--- reflection 2026-07-{14:02d}T10:{i:02d}:00 ---\n"
                f"**对话**: 测试对话 {i}\n"
                f"**完整性**: 完整\n"
                f"**工具利用**: 合理\n"
                f"**用户满意度**: 满意\n"
                f"**经验**: 经验教训 {i}\n"
                "---"
            )
        return "\n\n".join(blocks)

    def test_extract_recent_reflections(self):
        """6.1.7 从 20 条反思中正确提取最近 10 条。"""
        memory_text = self._make_memory_text(20)
        reflections = _extract_recent_reflections(memory_text, max_count=10)
        self.assertEqual(len(reflections), 10)
        # 最近的是经验教训 19
        self.assertIn("经验教训 19", reflections[-1])
        self.assertIn("经验教训 10", reflections[0])

    def test_extract_less_than_max(self):
        """少于 max_count 条时返回全部。"""
        memory_text = self._make_memory_text(3)
        reflections = _extract_recent_reflections(memory_text, max_count=10)
        self.assertEqual(len(reflections), 3)

    def test_extract_from_empty_text(self):
        """空文本返回空列表。"""
        self.assertEqual(_extract_recent_reflections(""), [])
        self.assertEqual(_extract_recent_reflections("   "), [])

    def test_extract_from_text_without_reflections(self):
        """无反思块的文本返回空列表。"""
        text = "这是一段普通的记忆文本\n没有反思块"
        self.assertEqual(_extract_recent_reflections(text), [])

    def test_extract_mixed_content(self):
        """混合普通记忆和反思块时只提取反思。"""
        text = (
            "用户喜欢喝咖啡\n\n"
            "--- reflection 2026-07-14T10:00:00 ---\n"
            "**对话**: 测试\n"
            "**经验**: 记住了用户偏好\n"
            "---\n\n"
            "用户也喜欢茶"
        )
        reflections = _extract_recent_reflections(text)
        self.assertEqual(len(reflections), 1)
        self.assertIn("记住了用户偏好", reflections[0])


class TestSummarizeUserMsg(unittest.TestCase):
    """_summarize_user_msg() 截断逻辑。"""

    def test_short_message(self):
        """短消息原样返回。"""
        self.assertEqual(_summarize_user_msg("你好"), "你好")

    def test_long_message_truncated(self):
        """长消息截断加省略号。"""
        long = "请帮我写一个 Python 脚本来处理 CSV 文件中的数据分析和可视化展示"
        result = _summarize_user_msg(long, max_len=10)
        self.assertEqual(len(result), 11)  # 10 + "…"
        self.assertTrue(result.endswith("…"))

    def test_empty_message(self):
        """空消息返回占位符。"""
        self.assertEqual(_summarize_user_msg(""), "(空)")
        self.assertEqual(_summarize_user_msg("  "), "(空)")


# ── 辅助函数 ──


def asyncio_run(coro):
    """同步运行异步协程（用于 unittest）。"""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 已在事件循环中（如 pytest-asyncio），通过线程安全方式等待
            fut = asyncio.run_coroutine_threadsafe(coro, loop)
            return fut.result(timeout=5)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ── 反思蒸馏测试 ──


class TestReflectionCompaction(unittest.TestCase):
    """测试反思蒸馏逻辑：parse、extract 两个纯函数。"""

    def test_parse_reflection_blocks(self):
        """_parse_reflection_blocks 正确提取所有反思块。"""
        from app.core.agent.reflector import _parse_reflection_blocks

        text = "角色记忆内容\n\n--- reflection 2026-07-01T10:00:00 ---\n**对话**: 问Python\n**经验**: 应该用代码示例\n---\n\n--- reflection 2026-07-02T10:00:00 ---\n**对话**: 问Go\n**经验**: 应该对比性能\n---"

        blocks = _parse_reflection_blocks(text)
        self.assertEqual(len(blocks), 2, f"应解析出 2 个块，实际 {len(blocks)}")
        self.assertIn("问Python", "\n".join(blocks[0]))
        self.assertIn("问Go", "\n".join(blocks[1]))

    def test_parse_reflection_blocks_empty(self):
        """无反思块时返回空列表。"""
        from app.core.agent.reflector import _parse_reflection_blocks

        blocks = _parse_reflection_blocks("只有角色记忆，没有反思")
        self.assertEqual(len(blocks), 0)
        blocks = _parse_reflection_blocks("")
        self.assertEqual(len(blocks), 0)

    def test_extract_non_reflection_content(self):
        """_extract_non_reflection_content 只返回反思块之前的内容。"""
        from app.core.agent.reflector import _extract_non_reflection_content

        text = "角色记忆内容\n\n这是角色的设定。\n\n--- reflection 2026-07-01T10:00:00 ---\n**经验**: 测试\n---"
        result = _extract_non_reflection_content(text)
        self.assertIn("角色记忆内容", result)
        self.assertIn("这是角色的设定", result)
        self.assertNotIn("reflection", result)

    def test_extract_non_reflection_no_reflections(self):
        """无反思时返回全部内容。"""
        from app.core.agent.reflector import _extract_non_reflection_content

        text = "纯角色记忆，没有反思"
        result = _extract_non_reflection_content(text)
        self.assertEqual(result, text)

    def test_reflection_count_triggers_compact(self):
        """超过 _MAX_RAW_REFLECTIONS 条时触发蒸馏判断。"""
        from app.core.agent.reflector import _MAX_RAW_REFLECTIONS, _parse_reflection_blocks

        # 不超过上限
        text = "角色记忆\n"
        for i in range(_MAX_RAW_REFLECTIONS):
            text += f"\n--- reflection 2026-07-{i + 1:02d}T10:00:00 ---\n**经验**: lesson{i}\n---"
        self.assertLessEqual(len(_parse_reflection_blocks(text)), _MAX_RAW_REFLECTIONS)

        # 超过上限
        text += "\n--- reflection 2026-07-30T10:00:00 ---\n**经验**: extra\n---"
        self.assertGreater(len(_parse_reflection_blocks(text)), _MAX_RAW_REFLECTIONS)

    def test_memory_text_rebuilt_with_distilled(self):
        """蒸馏后 memory_text 结构正确: 原始记忆 + 经验总结 + 最近反思。"""
        from app.core.agent.reflector import _parse_reflection_blocks, _KEEP_RECENT, _DISTILL_SUMMARY_HEADER
        from app.core.agent.reflector import _MAX_RAW_REFLECTIONS as MR

        # 构造 memory_text 模拟蒸馏后状态
        text = "角色记忆\n" + _DISTILL_SUMMARY_HEADER + "经验1\n经验2"
        for i in range(_KEEP_RECENT):
            text += f"\n--- reflection 2026-07-{i + 1:02d}T10:00:00 ---\n**经验**: recent{i}\n---"

        # 有经验总结
        self.assertIn(_DISTILL_SUMMARY_HEADER, text)
        # 反思不超过 _KEEP_RECENT
        blocks = _parse_reflection_blocks(text)
        self.assertEqual(len(blocks), _KEEP_RECENT)


if __name__ == "__main__":
    unittest.main()
