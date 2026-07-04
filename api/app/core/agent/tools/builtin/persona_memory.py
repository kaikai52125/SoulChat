"""角色记忆工具 —— 让 Agent 在对话中自己维护 persona.memory_text（MEMORY.md）。"""
import contextvars
import uuid as _uuid

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.agent.tools.base import ToolBuildContext, ToolSpec, register_tool
from app.models.agent_persona_model import AgentPersona

KEY = "save_to_persona_memory"

_current_persona_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "persona_memory.persona_id", default=None
)


def set_current_persona(persona_id: str | None) -> None:
    _current_persona_id.set(persona_id)


class _PersonaMemoryInput(BaseModel):
    content: str = Field(default="", description="要记住的内容。尽量简洁，只保留关键事实。")
    query: str = Field(default="", description="要记住的内容（与 content 等效）")
    operation: str = Field(
        default="append",
        description="'append' 追加到末尾；'replace' 覆写全部记忆",
    )


async def _build(_ctx: ToolBuildContext) -> StructuredTool:
    from sqlalchemy import select, update

    async def _run(content: str = "", query: str = "", operation: str = "append") -> str:
        text_to_save = (content or query).strip()
        if not text_to_save:
            return "错误：没有要保存的内容"
        pid = _current_persona_id.get()
        if not pid:
            return "错误：未检测到当前角色"

        try:
            pid_uuid = _uuid.UUID(pid)
        except (ValueError, TypeError):
            return "错误：角色 ID 无效"

        session = _ctx.session

        result = await session.execute(
            select(AgentPersona.memory_text).where(AgentPersona.id == pid_uuid)
        )
        row = result.one_or_none()
        if row is None:
            return "错误：角色不存在"

        current = (row[0] or "").strip()
        op = operation.strip().lower()

        if op == "replace":
            new_text = text_to_save
        else:
            new_text = (current + "\n\n" + text_to_save) if current else text_to_save

        await session.execute(
            update(AgentPersona)
            .where(AgentPersona.id == pid_uuid)
            .values(memory_text=new_text)
        )
        await session.commit()

        preview = new_text[:200] + ("..." if len(new_text) > 200 else "")
        return f"已保存。记忆长度 {len(new_text)} 字符。预览：{preview}"

    return StructuredTool.from_function(
        coroutine=_run,
        name=KEY,
        description=(
            "当对话中出现值得记住的用户信息（偏好、习惯、计划、重要决定等）时调用。"
            "只记对未来对话有用的关键事实，不要记琐碎信息。"
        ),
        args_schema=_PersonaMemoryInput,
    )


register_tool(
    ToolSpec(
        key=KEY,
        name="保存到角色记忆",
        icon="🧠",
        description="保存用户偏好/习惯/计划到当前角色记忆中，未来对话自动加载。",
        builder=_build,
        default_enabled=True,
    )
)
