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
from app.core.llm.chat_model import build_chat_model, get_default_chat_config
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
        """完整 Agent 循环：构建工具 → function calling → 返回结果。"""
        # 1. 构建模型
        try:
            config = await get_default_chat_config(session, user_id)
            model = build_chat_model(config, temperature=persona.temperature, streaming=False)
        except Exception as e:
            logger.error("agent-tool 构建 LLM 失败: %s", e)
            return f"（调用角色失败：模型配置错误 - {e}）"

        # 2. 构建工具 —— 按 persona 自己的配置，但排除 agent__* 防递归
        from app.core.agent.tools.registry import build_enabled_tools
        overrides = {
            "knowledge_search": getattr(persona, "enable_knowledge", True),
            "memory_search": getattr(persona, "enable_memory", True),
            "web_search": getattr(persona, "enable_web_search", False),
        }
        kb_ids = list(getattr(persona, "kb_ids", []) or [])
        enable_mcp = getattr(persona, "enable_mcp", False)
        mcp_server_ids = [str(s) for s in (getattr(persona, "mcp_server_ids", []) or [])]

        try:
            tools = await build_enabled_tools(
                session, user_id,
                citations=[],  # agent 调用不收集引用到主对话
                overrides=overrides,
                stats_holder={},
                kb_ids=kb_ids if kb_ids else None,
                enable_mcp=enable_mcp,
                mcp_server_ids=mcp_server_ids if mcp_server_ids else None,
                layered=True,  # 核心工具直接注入
            )
            # 过滤掉所有 agent__* 工具（防止递归调用）
            tools = [t for t in tools if not t.name.startswith("agent__")]
        except Exception as e:
            logger.warning("agent-tool 构建工具失败，降级为无工具: %s", e)
            tools = []

        # 3. 组装 system prompt
        from langchain_core.messages import HumanMessage, SystemMessage

        sys_content = prompt
        memory = (getattr(persona, "memory_text", "") or "").strip()
        if memory:
            sys_content = f"{sys_content}\n\n{memory}" if sys_content else memory

        messages: list = []
        if sys_content:
            messages.append(SystemMessage(content=sys_content))
        messages.append(HumanMessage(content=query))

        # 4. 运行 function calling Agent 循环
        # 注意：不在此创建 tracing span —— orchestrator 的 tool.ainvoke 外层
        # 已经有 agent_call span。内部 span（llm_call/tool_call）通过 OTel
        # contextvars 自动成为其子节点，天然形成"工具层级"嵌套。
        from app.core.agent.orchestrator import run_function_calling

        collected = ""
        try:
            async for ev in run_function_calling(model, tools, messages):
                if ev["type"] in ("token", "final"):
                    collected += ev.get("text", "")
        except Exception as e:
            logger.error("agent-tool function calling 失败: %s", e)
            return f"（调用角色「{persona.name}」时出错：{e}）"

        return collected.strip() or f"（角色「{persona.name}」未产生输出）"

    return StructuredTool.from_function(
        coroutine=_run,
        name=name,
        description=description,
        args_schema=CallAgentInput,
    )
