"""对话人格业务服务：CRUD + 设为当前生效。

角色 = Agent：人设提示词 + 工具配置 + 知识库 + 技能 + MEMORY.md + 上下文管理。
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.logging import get_logger
from app.core.storage import get_storage
from app.models.agent_persona_model import AgentPersona
from app.repositories.agent_persona_repository import AgentPersonaRepository
from app.schemas.agent_persona_schema import PersonaCreate, PersonaUpdate

logger = get_logger(__name__)

MAX_PERSONAS = 200


class AgentPersonaService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AgentPersonaRepository(session)

    async def list(
        self, user_id: uuid.UUID, include_group_only: bool = False
    ) -> list[AgentPersona]:
        items = await self.repo.list_by_user(user_id)
        if not items:
            from app.services.persona_scenario_builtins import DEFAULT_PERSONA

            default = AgentPersona(
                user_id=user_id,
                name=DEFAULT_PERSONA["name"],
                system_prompt=DEFAULT_PERSONA["system_prompt"],
                temperature=DEFAULT_PERSONA["temperature"],
                is_active=True,
            )
            await self.repo.add(default)
            items = await self.repo.list_by_user(user_id)
        if not include_group_only:
            items = [p for p in items if not p.in_group_only]
        return items

    async def _get_or_404(
        self, user_id: uuid.UUID, persona_id: uuid.UUID
    ) -> AgentPersona:
        persona = await self.repo.get(user_id, persona_id)
        if persona is None:
            raise BizError("角色不存在", code=4040, status_code=404)
        return persona

    @staticmethod
    def _apply_create(persona: AgentPersona, body: PersonaCreate) -> None:
        """从创建请求体写入 persona（__init__ 之后调用）。"""
        persona.name = body.name.strip()
        persona.avatar_key = body.avatar_key or None
        persona.system_prompt = body.system_prompt or ""
        persona.temperature = body.temperature

        persona.memory_text = body.memory_text or ""
        persona.tool_keys = list(body.tool_keys)
        persona.enable_knowledge = body.enable_knowledge
        persona.enable_memory = body.enable_memory
        persona.enable_web_search = body.enable_web_search
        persona.enable_mcp = body.enable_mcp
        persona.mcp_server_ids = list(body.mcp_server_ids) if body.mcp_server_ids else []
        persona.enable_active_recall = body.enable_active_recall
        persona.enable_cross_session = body.enable_cross_session
        persona.kb_ids = list(body.kb_ids)
        persona.conversation_scope = body.conversation_scope
        persona.context_window = body.context_window
        persona.human_mode = body.human_mode
        persona.show_avatar = body.show_avatar
        persona.allow_agent_call = body.allow_agent_call

    async def create(self, user_id: uuid.UUID, body: PersonaCreate) -> AgentPersona:
        if await self.repo.count(user_id) >= MAX_PERSONAS:
            raise BizError(f"角色数量已达上限（{MAX_PERSONAS}）", code=4041)
        persona = AgentPersona(user_id=user_id)
        self._apply_create(persona, body)
        if await self.repo.count(user_id) == 0:
            persona.is_active = True
        created = await self.repo.add(persona)
        logger.info("创建角色: user=%s persona=%s name=%s", user_id, created.id, created.name)
        return created

    async def update(
        self, user_id: uuid.UUID, persona_id: uuid.UUID, body: PersonaUpdate
    ) -> AgentPersona:
        persona = await self._get_or_404(user_id, persona_id)
        fields = body.model_dump(exclude_unset=True)

        _set_if = _set_if_not_none  # shorthand
        _set_if("name", persona, fields, transform=str.strip)
        _set_if("avatar_key", persona, fields, transform=lambda v: v or None)
        _set_if("system_prompt", persona, fields)
        _set_if("temperature", persona, fields)
        _set_if("memory_text", persona, fields)
        _set_if("tool_keys", persona, fields, transform=list)
        _set_if("enable_knowledge", persona, fields)
        _set_if("enable_memory", persona, fields)
        _set_if("enable_web_search", persona, fields)
        _set_if("enable_mcp", persona, fields)
        _set_if("mcp_server_ids", persona, fields, transform=list)
        _set_if("enable_active_recall", persona, fields)
        _set_if("enable_cross_session", persona, fields)
        _set_if("kb_ids", persona, fields, transform=list)
        _set_if("conversation_scope", persona, fields)
        _set_if("context_window", persona, fields)
        _set_if("human_mode", persona, fields)
        _set_if("show_avatar", persona, fields)
        _set_if("allow_agent_call", persona, fields)

        return await self.repo.save(persona)

    async def delete(self, user_id: uuid.UUID, persona_id: uuid.UUID) -> None:
        persona = await self._get_or_404(user_id, persona_id)
        await self.repo.delete(persona)
        logger.info("删除角色: user=%s persona=%s", user_id, persona_id)

    async def activate(self, user_id: uuid.UUID, persona_id: uuid.UUID) -> AgentPersona:
        persona = await self._get_or_404(user_id, persona_id)
        await self.repo.deactivate_all(user_id)
        persona.is_active = True
        saved = await self.repo.save(persona)
        logger.info("切换当前角色: user=%s persona=%s", user_id, persona_id)
        return saved

    @staticmethod
    def to_out_dict(persona: AgentPersona) -> dict:
        avatar_url = None
        if persona.avatar_key:
            try:
                avatar_url = get_storage().get_url(persona.avatar_key)
            except Exception as e:
                logger.warning("角色头像 url 生成失败: key=%s err=%s", persona.avatar_key, e)
        return {
            "id": str(persona.id),
            "name": persona.name,
            "avatar_key": persona.avatar_key,
            "avatar_url": avatar_url,
            "system_prompt": persona.system_prompt,
            "temperature": persona.temperature,
            "is_active": persona.is_active,
            "memory_text": persona.memory_text,
            "tool_keys": persona.tool_keys or [],
            "enable_knowledge": persona.enable_knowledge,
            "enable_memory": persona.enable_memory,
            "enable_web_search": persona.enable_web_search,
            "enable_mcp": persona.enable_mcp,
            "mcp_server_ids": persona.mcp_server_ids or [],
            "enable_active_recall": persona.enable_active_recall,
            "enable_cross_session": persona.enable_cross_session,
            "kb_ids": persona.kb_ids or [],
            "conversation_scope": persona.conversation_scope,
            "context_window": persona.context_window,
            "human_mode": persona.human_mode,
            "show_avatar": persona.show_avatar,
            "allow_agent_call": persona.allow_agent_call,
        }


    async def get_stats(self, user_id: uuid.UUID, persona_id: uuid.UUID) -> dict:
        """获取角色使用统计（含单聊 + 群聊）。"""
        await self._get_or_404(user_id, persona_id)
        from sqlalchemy import func, select, or_
        from app.models.conversation_model import Conversation, Message
        from app.models.skill_model import Skill
        from app.models.agent_trace_model import AgentTrace, AgentSpan

        pid_str = str(persona_id)

        # 对话数：单聊归属 + 群聊中作为成员
        conv_count = await self.session.scalar(
            select(func.count(Conversation.id)).where(
                or_(
                    Conversation.persona_id == persona_id,
                    Conversation.member_persona_ids.contains([pid_str]),
                )
            )
        ) or 0

        # 回复数：该角色发出的所有 assistant 消息（单聊+群聊）
        msg_count = await self.session.scalar(
            select(func.count(Message.id)).where(
                Message.sender_persona_id == persona_id,
                Message.role == "assistant",
            )
        ) or 0

        # 工具调用次数（从 tracing 数据）
        tool_calls = await self.session.scalar(
            select(func.count(AgentSpan.id)).where(
                AgentSpan.trace_id.in_(
                    select(AgentTrace.trace_id).where(AgentTrace.persona_id == persona_id)
                ),
                AgentSpan.span_type == "tool_call",
            )
        ) or 0

        # 总对话轮次（traces）
        trace_count = await self.session.scalar(
            select(func.count(AgentTrace.trace_id)).where(
                AgentTrace.persona_id == persona_id
            )
        ) or 0

        # 总成本
        total_cost = await self.session.scalar(
            select(func.coalesce(func.sum(AgentTrace.total_cost_cny), 0.0)).where(
                AgentTrace.persona_id == persona_id
            )
        ) or 0.0

        # 技能数 + 技能总调用次数
        skill_count = await self.session.scalar(
            select(func.count(Skill.id)).where(Skill.persona_id == persona_id, Skill.enabled.is_(True))
        ) or 0

        total_skill_calls = await self.session.scalar(
            select(func.coalesce(func.sum(Skill.call_count), 0)).where(
                Skill.persona_id == persona_id
            )
        ) or 0

        # MCP 工具调用次数（从 tracing）
        mcp_calls = await self.session.scalar(
            select(func.count(AgentSpan.id)).where(
                AgentSpan.trace_id.in_(
                    select(AgentTrace.trace_id).where(AgentTrace.persona_id == persona_id)
                ),
                AgentSpan.span_type == "mcp_call",
            )
        ) or 0

        return {
            "conversations": conv_count,
            "messages": msg_count,
            "tool_calls": tool_calls,
            "mcp_calls": mcp_calls,
            "traces": trace_count,
            "total_cost_cny": round(float(total_cost), 4),
            "skills": skill_count,
            "skill_calls": total_skill_calls,
        }


def _set_if_not_none(
    key: str,
    obj: object,
    fields: dict,
    *,
    transform=None,
) -> None:
    """fields 中存在且值不为 None 时，写入 obj.key，可选 transform。"""
    if key not in fields or fields[key] is None:
        return
    val = fields[key]
    if transform is not None:
        val = transform(val)
    setattr(obj, key, val)
