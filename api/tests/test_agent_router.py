"""AgentRouter 消息分类器单元测试。

覆盖：4 路路由分类、置信度阈值警告、异常回退、模型复用。
"""
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.core.agent.router import AgentRouter, build_tools_summary


# ---------------------------------------------------------------------------
# Mock 模型工厂
# ---------------------------------------------------------------------------
def _make_router_model(json_response: str) -> MagicMock:
    """创建一个模拟的 ChatOpenAI model，ainvoke 返回指定 JSON。"""
    model = MagicMock()
    model.model_name = "test-router-model"

    async def _ainvoke(messages):
        return AIMessage(content=json_response)

    model.ainvoke = _ainvoke
    return model


def _make_failing_model() -> MagicMock:
    """创建一个 ainvoke 抛出异常的模拟模型。"""
    model = MagicMock()
    model.model_name = "test-router-model"

    async def _ainvoke(messages):
        raise RuntimeError("LLM 调用失败")

    model.ainvoke = _ainvoke
    return model


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

class TestRouterClassify:
    """7.1 AgentRouter 分类功能测试。"""

    @pytest.mark.asyncio
    async def test_classify_trivial(self):
        """7.1.1 "你好"→route="trivial" """
        model = _make_router_model(
            '{"route": "trivial", "confidence": 0.95, "reason": "纯问候"}'
        )
        router = AgentRouter(model)
        result = await router.classify("你好", "knowledge_search, web_search")
        assert result.route == "trivial"
        assert result.confidence >= 0.9
        assert len(result.reason) > 0

    @pytest.mark.asyncio
    async def test_classify_trivial_thanks(self):
        """"谢谢"→"trivial" """
        model = _make_router_model(
            '{"route": "trivial", "confidence": 0.98, "reason": "简单感谢"}'
        )
        router = AgentRouter(model)
        result = await router.classify("谢谢", "knowledge_search, web_search")
        assert result.route == "trivial"

    @pytest.mark.asyncio
    async def test_classify_trivial_weather(self):
        """"今天天气不错"→"trivial" """
        model = _make_router_model(
            '{"route": "trivial", "confidence": 0.85, "reason": "天气闲聊"}'
        )
        router = AgentRouter(model)
        result = await router.classify("今天天气不错", "knowledge_search, web_search")
        assert result.route == "trivial"

    @pytest.mark.asyncio
    async def test_classify_chat(self):
        """7.1.2 "你觉得 Python 怎么样"→route="chat" """
        model = _make_router_model(
            '{"route": "chat", "confidence": 0.88, "reason": "对话性但需实质回答"}'
        )
        router = AgentRouter(model)
        result = await router.classify("你觉得 Python 怎么样", "knowledge_search, web_search")
        assert result.route == "chat"

    @pytest.mark.asyncio
    async def test_classify_chat_closure(self):
        """"给我解释闭包"→"chat" """
        model = _make_router_model(
            '{"route": "chat", "confidence": 0.85, "reason": "需要解释概念"}'
        )
        router = AgentRouter(model)
        result = await router.classify("给我解释闭包", "knowledge_search, web_search")
        assert result.route == "chat"

    @pytest.mark.asyncio
    async def test_classify_single_tool(self):
        """7.1.3 "帮我查知识库里关于 Python 的文档"→route="single_tool" """
        model = _make_router_model(
            '{"route": "single_tool", "confidence": 0.92, "reason": "需要查询知识库"}'
        )
        router = AgentRouter(model)
        result = await router.classify(
            "帮我查知识库里关于 Python 的文档",
            "knowledge_search, web_search",
        )
        assert result.route == "single_tool"

    @pytest.mark.asyncio
    async def test_classify_multi_step(self):
        """7.1.4 "比较 Python 和 Go 的性能，各找 3 个 benchmark，用表格输出"→route="multi_step" """
        model = _make_router_model(
            '{"route": "multi_step", "confidence": 0.90, "reason": "需要多步比较"}'
        )
        router = AgentRouter(model)
        result = await router.classify(
            "比较 Python 和 Go 的性能，各找 3 个 benchmark，用表格输出",
            "knowledge_search, web_search",
        )
        assert result.route == "multi_step"

    @pytest.mark.asyncio
    async def test_confidence_threshold(self):
        """7.1.5 confidence < 0.7 时记录 warning 日志（路由结果照常使用）。"""
        model = _make_router_model(
            '{"route": "multi_step", "confidence": 0.45, "reason": "不确定但可能复杂"}'
        )
        router = AgentRouter(model)
        with patch("app.core.agent.router.logger") as mock_logger:
            result = await router.classify("帮我做个复杂任务", "knowledge_search, web_search")
            assert result.route == "multi_step"
            assert result.confidence == 0.45
            # 验证 warning 日志被记录
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_fallback(self):
        """7.1.6 LLM 调用抛异常 → RouteResult(route="single_tool", confidence=0)。"""
        model = _make_failing_model()
        router = AgentRouter(model)
        result = await router.classify("任何消息", "knowledge_search, web_search")
        assert result.route == "single_tool"
        assert result.confidence == 0.0
        assert result.reason == "router error"

    @pytest.mark.asyncio
    async def test_model_reuse(self):
        """7.1.7 router_model=None 时复用聊天模型（在本测试中即传入的 model）。"""
        model = _make_router_model(
            '{"route": "trivial", "confidence": 0.95, "reason": "测试"}'
        )
        # AgentRouter 直接用传入的 model，不额外构建
        router = AgentRouter(model)
        result = await router.classify("你好", "")
        assert result.route == "trivial"
        # 验证使用的是传入的 model
        assert router._model is model

    @pytest.mark.asyncio
    async def test_invalid_route_fallback(self):
        """Router 返回无效路由 → 回退到 single_tool。"""
        model = _make_router_model(
            '{"route": "invalid_route", "confidence": 0.9, "reason": "测试"}'
        )
        router = AgentRouter(model)
        result = await router.classify("测试", "")
        assert result.route == "single_tool"
        assert result.confidence == 0.0


class TestBuildToolsSummary:
    """build_tools_summary 工具函数测试。"""

    def test_with_tools(self):
        """有工具列表时返回摘要字符串。"""
        tool1 = MagicMock(name="knowledge_search", description="知识库搜索工具")
        tool2 = MagicMock(name="web_search", description="联网搜索工具")
        summary = build_tools_summary([tool1, tool2])
        assert "knowledge_search" in summary
        assert "web_search" in summary
        assert "知识库搜索" in summary

    def test_empty_tools(self):
        """无工具时返回占位字符串。"""
        summary = build_tools_summary([])
        assert "无可用工具" in summary

    def test_none_tools(self):
        """工具列表为 None/空列表时的处理。"""
        summary = build_tools_summary([])
        assert summary == "（无可用工具）"
