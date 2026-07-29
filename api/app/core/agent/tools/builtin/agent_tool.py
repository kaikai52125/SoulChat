"""Agent-as-Tool 构造器 —— 把角色包装为可被其他角色调用的 StructuredTool。

工具名格式：``agent__{slug}``。被调用的角色是**完整的 Agent**：
- 拥有自己的 persona 配置（system_prompt / memory_text / temperature）
- 拥有自己启用的工具（knowledge / memory / web / datetime / MCP / skill）
- 通过 function calling 循环自主推理
- 唯一限制：不挂载 agent__* 工具（防止递归调用）
"""
import re

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.agent.tools.base import ToolBuildContext
from app.core.logging import get_logger

logger = get_logger(__name__)


def _slugify(name: str) -> str:
    s = re.sub(r"[^\w]", "_", name, flags=re.UNICODE)
    s = re.sub(r"_+", "_", s)
    return s.strip("_").lower()


class CallAgentInput(BaseModel):
    query: str = Field(..., description="要问这个角色的问题")


async def build_agent_tool(persona, ctx: ToolBuildContext) -> StructuredTool | None:
    """将 AgentPersona 包装为完整的 Agent 工具。

    被调用时，角色以完整 Agent 身份运行 function calling 循环，
    拥有自己的 tools（knowledge/memory/web/datetime/MCP/skill），
    但不挂载其他 agent__* 工具（防止 A→B→C 递归）。
    """
    slug = _slugify(persona.name)
    name = f"agent__{slug}"

    prompt = (persona.system_prompt or "").strip()
    short_desc = (prompt[:97] + "...") if len(prompt) > 100 else prompt
    description = f"调用角色「{persona.name}」：{short_desc}" if short_desc else f"调用角色「{persona.name}」"

    session = ctx.session
    user_id = ctx.user_id

    async def _run(query: str) -> str:
        """完整 Agent 循环：复用 build_persona_agent() 构建，拥有完整 Skill 能力。"""
        from app.core.agent.persona_agent import build_persona_agent
        from app.core.agent.tools.builtin.persona_memory import (
            set_current_persona,
            get_current_persona_id,
        )

        # 1. 构建完整角色 Agent（含 Skill 加载、prompt 注入、脚本工具、tool_keys 白名单）
        #    build_persona_agent 内部已过滤 agent__* 工具，不会递归调用
        try:
            agent = await build_persona_agent(session, persona.id, user_id)
        except Exception as e:
            logger.error("agent-tool 构建角色 Agent 失败: %s", e)
            return f"（调用角色「{persona.name}」失败：{e}）"

        if agent is None:
            return f"（角色「{persona.name}」不存在或已被删除）"

        # 2. 切换上下文：让 skill_load / bash_tool 等工具感知当前是被调用角色
        prev_persona_id = get_current_persona_id()
        set_current_persona(str(persona.id))
        try:
            # 3. 组装消息
            from langchain_core.messages import HumanMessage, SystemMessage

            messages: list = []
            if agent.system_prompt:
                messages.append(SystemMessage(content=agent.system_prompt))
            messages.append(HumanMessage(content=query))

            # 4. 运行 function calling Agent 循环
            # 注意：不在此创建 tracing span —— orchestrator 的 tool.ainvoke 外层
            # 已经有 agent_call span。内部 span（llm_call/tool_call）通过 OTel
            # contextvars 自动成为其子节点，天然形成"工具层级"嵌套。
            from app.core.agent.orchestrator import run_function_calling

            collected = ""
            try:
                async for ev in run_function_calling(agent.model, agent.tools, messages):
                    if ev["type"] in ("token", "final"):
                        collected += ev.get("text", "")
            except Exception as e:
                logger.error("agent-tool function calling 失败: %s", e)
                return f"（调用角色「{persona.name}」时出错：{e}）"

            return collected.strip() or f"（角色「{persona.name}」未产生输出）"
        finally:
            set_current_persona(prev_persona_id)

    return StructuredTool.from_function(
        coroutine=_run,
        name=name,
        description=description,
        args_schema=CallAgentInput,
    )
