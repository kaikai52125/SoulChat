"""skill_load 工具：Agent 按需加载角色的非驻留 Skill。

返回 Skill 的 prompt + 建议工具 + 可用脚本清单 + bash 执行示例。
"""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.agent.tools.base import ToolBuildContext, ToolSpec, register_tool
from app.core.logging import get_logger

logger = get_logger(__name__)

KEY = "skill_load"


class _SkillLoadInput(BaseModel):
    query: str = Field(..., description="要加载的技能名称（完整名称或关键词）")


async def _build(ctx: ToolBuildContext) -> StructuredTool | None:
    session = ctx.session
    user_id = ctx.user_id

    async def _run(query: str) -> str:
        """加载指定技能，返回完整能力描述。"""
        query = query.strip()
        if not query:
            return "错误：请提供技能名称"

        try:
            from app.repositories.agent_persona_repository import AgentPersonaRepository
            from app.repositories.skill_repository import SkillRepository

            persona = await AgentPersonaRepository(session).get_active(user_id)
            if persona is None:
                return "错误：未找到活跃角色"

            all_skills = await SkillRepository(session).list_by_persona(persona.id)
            # 仅筛选按需 Skill（is_resident=False 或 config.is_resident=False）
            on_demand = [
                s for s in all_skills
                if s.enabled and not _is_resident(s)
            ]

            if not on_demand:
                return "当前角色没有可用的按需技能。所有技能均已常驻生效。"

            # 匹配技能：精确匹配 name 或模糊包含
            matched = None
            for s in on_demand:
                if s.name.strip().lower() == query.lower():
                    matched = s
                    break

            if matched is None:
                for s in on_demand:
                    if query.lower() in s.name.lower():
                        matched = s
                        break

            if matched is None:
                available = "、".join(s.name for s in on_demand)
                return f"未找到技能「{query}」。可用技能：{available}"

            return _format_skill(matched)

        except Exception as e:
            logger.error("skill_load 查询失败: %s", e)
            return f"技能加载失败：{e}"

    return StructuredTool.from_function(
        coroutine=_run,
        name=KEY,
        description=(
            "技能加载：当你需要某项专业技能但当前工具列表中找不到时，"
            "使用此工具按名称加载。加载后你会获得该技能的详细说明、"
            "可用脚本列表及其执行方式。"
        ),
        args_schema=_SkillLoadInput,
    )


def _is_resident(skill) -> bool:
    """判断 Skill 是否为常驻模式。默认为 True（向后兼容）。"""
    config = skill.config or {}
    return config.get("is_resident", True)


def _format_skill(skill) -> str:
    """格式化 Skill 信息供 Agent 使用。"""
    lines = [f"【技能】{skill.name}"]

    if skill.description:
        lines.append(f"说明：{skill.description}")

    prompt = (skill.prompt or "").strip()
    if prompt:
        lines.append(f"\n【任务提示词】\n{prompt}")

    tool_keys = skill.tool_keys or []
    if tool_keys:
        lines.append(f"\n【建议使用的内置工具】{', '.join(tool_keys)}")

    # 脚本工具
    config = skill.config or {}
    tools_def = config.get("tools") or []
    if tools_def and isinstance(tools_def, list):
        lines.append("\n【可用脚本】")
        lines.append("使用 bash 工具执行以下脚本（已在技能目录中）：")
        for td in tools_def:
            if not isinstance(td, dict):
                continue
            t_name = td.get("name", "?")
            t_desc = td.get("description", "")
            t_script = td.get("script", "")
            lines.append(f"\n  • {t_name}")
            if t_desc:
                lines.append(f"    描述：{t_desc}")
            if t_script:
                lines.append(f"    执行：bash(\"python {t_script} <参数>\")")

    lines.append("\n请基于以上信息，使用 bash 工具执行相关脚本完成任务。")
    return "\n".join(lines)


register_tool(
    ToolSpec(
        key=KEY,
        name="技能加载",
        description="按需加载角色的非驻留技能，获取其提示词、建议工具和可用脚本清单。",
        icon="📦",
        builder=_build,
        default_enabled=True,
        layer="core",
    )
)
