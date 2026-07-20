"""角色 Agent 构建器：单聊、群聊社交模式、群聊任务模式共享同一套构建逻辑。

用法:
    agent = await build_persona_agent(session, persona_id, owner_id)
    # agent.model, agent.tools, agent.system_prompt

返回的 Agent 已包含:
  - 角色的 system_prompt + memory_text
  - 角色的内置工具 (enable_knowledge/memory/web_search)
  - 角色的 MCP 工具 (enable_mcp + mcp_server_ids)
  - 角色的常驻 Skill (prompt 注入 + tool_keys 白名单 + 脚本工具注册)
  - 按需 Skill 提示
  - 时效性提示 + 并行策略提示
"""
import uuid
from dataclasses import dataclass, field

from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI


@dataclass
class PersonaAgent:
    """完整的角色 Agent 配置。"""
    model: ChatOpenAI
    tools: list[BaseTool] = field(default_factory=list)
    system_prompt: str = ""


async def build_persona_agent(
    session,
    persona_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> PersonaAgent | None:
    """为指定角色构建完整 Agent（model + tools + system_prompt）。

    从 DB 加载角色的全部配置，构建与单聊完全一致的 Agent。
    不包含请求级别的覆盖（如 body 临时开关工具/two-speed 路由等）。
    """
    from app.core.llm.chat_model import build_chat_model, get_default_chat_config
    from app.core.agent.tools import build_enabled_tools
    from app.core.agent.context_hint import current_context_block
    from app.repositories.agent_persona_repository import AgentPersonaRepository
    from app.repositories.skill_repository import SkillRepository
    from app.core.logging import get_logger

    logger = get_logger(__name__)

    # ── 1. 加载角色 ──
    persona = await AgentPersonaRepository(session).get(owner_id, persona_id)
    if persona is None:
        return None

    # ── 2. 加载 Skill ──
    all_skills = [
        s for s in await SkillRepository(session).list_by_persona(persona_id)
        if s.enabled
    ]
    resident_skills = [s for s in all_skills if _skill_is_resident(s)]
    on_demand_skills = [s for s in all_skills if not _skill_is_resident(s)]

    # ── 3. 构建 LLM 模型 ──
    config = await get_default_chat_config(session, owner_id)
    model = build_chat_model(config, temperature=persona.temperature, streaming=True)

    # ── 4. 构建工具 ──
    overrides = {
        "knowledge_search": persona.enable_knowledge,
        "memory_search": persona.enable_memory,
        "web_search": persona.enable_web_search,
    }
    kb_ids = list(persona.kb_ids) if persona.kb_ids else None
    tools = await build_enabled_tools(
        session, owner_id,
        citations=[],
        overrides=overrides,
        stats_holder={},
        kb_ids=kb_ids,
        enable_mcp=persona.enable_mcp,
        mcp_server_ids=[str(s) for s in (persona.mcp_server_ids or [])] if persona.mcp_server_ids else None,
        layered=True,
    )
    # 过滤 agent__* 工具（Worker 不应互相调用）
    tools = [t for t in tools if not t.name.startswith("agent__")]

    # ── 5. Skill tool_keys 白名单 ──
    if resident_skills:
        all_tool_keys: set[str] = set()
        for s in resident_skills:
            if s.tool_keys:
                all_tool_keys.update(s.tool_keys)
        if all_tool_keys:
            tools = [t for t in tools if t.name in all_tool_keys]

    # ── 6. Skill 脚本工具 ──
    for s in resident_skills:
        if s.storage_path and s.config.get("tools"):
            try:
                from app.core.agent.tools.skill_executor import build_skill_tools
                st = build_skill_tools(
                    skill_id=s.id, skill_config=s.config,
                    skill_dir=s.storage_path, record_call=None,
                    session=session, user_id=owner_id,
                )
                tools.extend(st)
            except Exception as e:
                logger.warning("角色 %s Skill 脚本工具构建失败: %s err=%s", persona.name, s.name, e)

    # ── 7. 组装 system_prompt ──
    parts: list[str] = []

    system_prompt = (persona.system_prompt or "").strip()
    if system_prompt:
        parts.append(system_prompt)

    memory = (persona.memory_text or "").strip()
    if memory:
        parts.append(f"【角色记忆】\n{memory}")

    for sk in resident_skills:
        skill_prompt = (sk.prompt or "").strip()
        if skill_prompt:
            parts.append(f"【当前任务能力：{sk.name}】\n{skill_prompt}")

    # 时效性提示
    parts.append(current_context_block(with_tool_hint=bool(tools)))

    prompt_text = "\n\n".join(parts)

    # ── 8. 按需 Skill 提示 ──
    if on_demand_skills:
        lines = ["【可按需加载的技能】使用时调用 skill_load 工具加载："]
        for s in on_demand_skills:
            desc = (s.description or "").strip()
            script_names: list[str] = []
            tdef = (s.config or {}).get("tools") or []
            if isinstance(tdef, list):
                for td in tdef:
                    if isinstance(td, dict) and td.get("name"):
                        script_names.append(td["name"])
            meta = s.name
            if desc:
                meta += f"：{desc}"
            if script_names:
                meta += f"（可用脚本：{', '.join(script_names)}）"
            if s.tool_keys:
                meta += f"（建议内置工具：{', '.join(s.tool_keys)}）"
            lines.append(f"  • {meta}")
        prompt_text = prompt_text + "\n\n" + "\n".join(lines)

    # ── 9. 并行策略提示 ──
    if tools:
        parallel_hint = (
            "当你面对需要多步检索或对比分析的复杂问题时，请先在脑中规划需要哪些信息，"
            "然后在同一轮中同时调用多个互相独立的工具（系统会并行执行），"
            "最后基于所有结果综合回答。不要一步步串行调用可以并行的工具。"
        )
        prompt_text = prompt_text + "\n\n" + parallel_hint

    return PersonaAgent(model=model, tools=tools, system_prompt=prompt_text.strip())


def _skill_is_resident(skill) -> bool:
    """判断 Skill 是否为常驻模式。默认 True。"""
    config = skill.config or {}
    return config.get("is_resident", True)
