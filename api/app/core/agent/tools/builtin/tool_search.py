"""工具查找工具：Agent 在需要扩展工具时调用，按意图语义搜索并返回最相关工具的列表。

通过 tool_search，Agent 可以动态发现 MCP Server 工具、Skill 工具等扩展工具，
而不需要所有工具的 schema 全量注入 prompt。
"""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.agent.tools.base import ToolBuildContext, ToolSpec, register_tool
from app.core.logging import get_logger

logger = get_logger(__name__)

KEY = "tool_search"


class _ToolSearchInput(BaseModel):
    intent: str = Field(..., description="你想完成什么操作？用自然语言描述意图")
    top_k: int = Field(default=5, ge=1, le=10, description="最多返回几个工具（1-10）")


async def _build(ctx: ToolBuildContext) -> StructuredTool | None:
    from app.core.agent.tools.registry import search_tools

    async def _run(intent: str, top_k: int = 5) -> str:
        try:
            results = await search_tools(
                intent=intent,
                top_k=top_k,
                session=ctx.session,
                user_id=ctx.user_id,
            )
        except Exception as e:
            logger.warning("工具查找失败: %s", e)
            return f"工具查找失败：{e}"

        if not results:
            return "没有找到相关的扩展工具。请尝试调整意图描述，或直接使用内置工具完成。\n"

        lines = [f"找到 {len(results)} 个相关工具：\n"]
        for i, r in enumerate(results, 1):
            name = r.get("name", r["key"])
            desc = r.get("description", "")
            line = f"{i}. {r['key']} —— {name}"
            if desc:
                line += f"\n   说明：{desc[:200]}"
            lines.append(line)

        return "\n\n".join(lines)

    return StructuredTool.from_function(
        coroutine=_run,
        name=KEY,
        description="工具查找：当内置工具（知识库搜索、记忆搜索、联网、时间等）无法满足当前需求时，"
                    "使用此工具查找可用的扩展工具。输入你的意图描述，系统会返回最相关的工具列表。",
        args_schema=_ToolSearchInput,
    )


register_tool(
    ToolSpec(
        key=KEY,
        name="工具查找",
        description="按意图查找可用的扩展工具（MCP 工具、技能工具等）。当当前工具集不足以完成任务时使用。",
        icon="🔍",
        builder=_build,
        default_enabled=True,
        layer="core",
    )
)
