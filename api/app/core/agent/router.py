"""AgentRouter: 轻量消息分类器，2 路路由（chat/tool）。

用法:
    router = AgentRouter(model)
    result = await router.classify("你好", "知识库搜索, 联网搜索")
    # RouteResult(route="chat", confidence=0.95, reason="纯问候")
"""
import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.core.agent.prompt_renderer import render_agent_prompt
from app.core.logging import get_logger

logger = get_logger(__name__)


class RouteResult(BaseModel):
    """路由分类结果。"""
    route: Literal["chat", "tool"]
    confidence: float
    reason: str


class AgentRouter:
    """用 LLM 对用户消息做 2 路路由分类，决定是否挂载工具。

    设计目标：
    - prompt 极短（~200 token），用最轻量模型，目标 < 500ms
    - 异常时防御性回退到 tool（保守选择，保留工具能力）
    - 支持配置 router_model 切换轻量模型，None 时复用聊天模型
    """

    def __init__(self, model: ChatOpenAI):
        self._model = model

    async def classify(
        self, message: str, available_tools_summary: str
    ) -> RouteResult:
        """对用户消息进行分类。

        Args:
            message: 用户输入文本。
            available_tools_summary: 可用工具描述。

        Returns:
            RouteResult: 路由分类结果。异常时返回 route="tool" 的防御性结果。
        """
        prompt = render_agent_prompt(
            "router.jinja2",
            message=message,
            tools_summary=available_tools_summary,
        )
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content="请分类并返回 JSON。"),
        ]
        try:
            resp = await self._model.ainvoke(messages)
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            parsed = self._extract_json(text)
            route = parsed.get("route", "tool")
            confidence = float(parsed.get("confidence", 0.0))
            reason = str(parsed.get("reason", ""))
            # 校验 route 合法性
            if route not in ("chat", "tool"):
                logger.warning("Router 返回无效路由 %s，回退到 tool", route)
                route = "tool"
                confidence = 0.0
                reason = "无效路由"
            if confidence < 0.7:
                logger.warning(
                    "Router 置信度偏低: route=%s confidence=%.2f reason=%s",
                    route, confidence, reason,
                )
            return RouteResult(route=route, confidence=confidence, reason=reason)
        except Exception as e:
            logger.warning("Router 分类失败（回退到 tool）: %s", e)
            return RouteResult(
                route="tool", confidence=0.0, reason="router error",
            )

    @staticmethod
    def _extract_json(text: str) -> dict:
        """从 LLM 输出中提取 JSON 对象。优先尝试完整解析，否则用正则提取。"""
        text = text.strip()
        # 直接尝试解析
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass
        # 尝试提取 ```json ... ``` 块
        import re as _re
        m = _re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, _re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except (json.JSONDecodeError, ValueError):
                pass
        # 尝试提取 {...} 块
        m = _re.search(r"\{.*\}", text, _re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except (json.JSONDecodeError, ValueError):
                pass
        raise ValueError(f"无法从 LLM 输出中提取 JSON: {text[:200]}")


def build_tools_summary(tools: list) -> str:
    """构建工具摘要字符串，供 Router/Planner 使用。

    从工具列表提取 (name, description)，拼接为简短摘要。
    工具列表为空时返回 "（无可用工具）"。
    """
    if not tools:
        return "（无可用工具）"
    parts: list[str] = []
    for t in tools:
        name = getattr(t, "name", str(t))
        desc = getattr(t, "description", "")
        if desc:
            parts.append(f"{name}: {desc[:120]}")
        else:
            parts.append(name)
    return " | ".join(parts)


__all__ = ["AgentRouter", "RouteResult", "build_tools_summary"]
