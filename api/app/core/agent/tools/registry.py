"""工具注册中心：按用户启停构建 Agent 可用的工具列表，并提供工具列表查询。

启停优先级：本轮 overrides（对话请求临时开关） > 用户 tool_configs 持久配置 > ToolSpec.default_enabled。

动态工具发现（v0.6）：
- 核心工具（layer="core"）始终注入 prompt
- 扩展工具（layer="extended"，如 MCP/Skill）通过 tool_search 按需发现
- 工具 embedding 预计算并缓存于 _TOOL_EMBEDDING_CACHE，search_tools 做内存余弦相似度匹配
"""
import math
import uuid
from contextlib import asynccontextmanager

from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.agent.tools.builtin  # noqa: F401  触发内置工具注册
from app.core.agent.tools.base import BUILTIN_REGISTRY, ToolBuildContext
from app.core.logging import get_logger
from app.repositories.tool_config_repository import ToolConfigRepository

logger = get_logger(__name__)

# ── 工具 embedding 缓存 ──────────────────────────────────────────────
# key → vector，用于 tool_search 的语义匹配。核心工具在 build 时预计算，
# MCP/Skill 工具在各加载函数中写入。
_TOOL_EMBEDDING_CACHE: dict[str, list[float]] = {}
_EMBEDDING_DIMENSIONS = 1024  # 与 settings.embedding_dims 对齐
_MIN_SIMILARITY = 0.3  # search_tools 的最低余弦相似度阈值


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """余旋相似度。"""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def _get_embed_client(session: AsyncSession, user_id: uuid.UUID):
    """获取 embedding client（可选，无配置时返回 None）。"""
    from app.core.llm.resolver import get_optional_client_for_type

    return await get_optional_client_for_type(session, user_id, "embedding")


async def _compute_and_cache_embedding(
    key: str, name: str, description: str,
    session: AsyncSession | None = None,
    user_id: uuid.UUID | None = None,
) -> list[float] | None:
    """计算工具 embedding 并写入 _TOOL_EMBEDDING_CACHE。

    已缓存则直接返回。session/user_id 为 None 时尝试从本地已有缓存取。
    """
    if key in _TOOL_EMBEDDING_CACHE:
        return _TOOL_EMBEDDING_CACHE[key]
    if session is None or user_id is None:
        return None
    embed_client = await _get_embed_client(session, user_id)
    if embed_client is None:
        return None
    text = f"{key}: {name} —— {description}"
    vec = await embed_client.embed_one(text, dimensions=_EMBEDDING_DIMENSIONS)
    _TOOL_EMBEDDING_CACHE[key] = vec
    return vec


def invalidate_tool_embedding(key: str) -> None:
    """清除指定工具的 embedding 缓存。"""
    _TOOL_EMBEDDING_CACHE.pop(key, None)


async def _precompute_core_embeddings(
    session: AsyncSession, user_id: uuid.UUID,
) -> None:
    """预计算所有核心内置工具的 embedding（缺失时计算）。"""
    for key, spec in BUILTIN_REGISTRY.items():
        if spec.layer != "core":
            continue
        if key in _TOOL_EMBEDDING_CACHE:
            continue
        try:
            await _compute_and_cache_embedding(
                key, spec.name, spec.description,
                session=session, user_id=user_id,
            )
        except Exception as e:
            logger.warning("预计算工具 embedding 失败（跳过）: %s: %s", key, e)


async def search_tools(
    intent: str,
    top_k: int = 5,
    session: AsyncSession | None = None,
    user_id: uuid.UUID | None = None,
) -> list[dict]:
    """按意图语义搜索工具。

    计算 intent embedding，与 _TOOL_EMBEDDING_CACHE 中所有工具做余弦相似度，
    返回 Top-K（按相似度降序）。相似度低于 _MIN_SIMILARITY 的工具不返回。

    返回格式：[{key, name, description, similarity}]
    """
    if session is not None and user_id is not None:
        # 尝试补齐核心工具 embedding
        await _precompute_core_embeddings(session, user_id)

    if not _TOOL_EMBEDDING_CACHE:
        return []

    embed_client = None
    if session is not None and user_id is not None:
        embed_client = await _get_embed_client(session, user_id)
    if embed_client is None:
        logger.warning("search_tools: 无 embedding 客户端可用")
        return []

    intent_vec = await embed_client.embed_one(intent, dimensions=_EMBEDDING_DIMENSIONS)

    scored: list[tuple[float, str]] = []
    for key, vec in _TOOL_EMBEDDING_CACHE.items():
        sim = _cosine_similarity(intent_vec, vec)
        if sim >= _MIN_SIMILARITY:
            scored.append((sim, key))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    # 从 BUILTIN_REGISTRY 查找工具元信息
    result: list[dict] = []
    for sim, key in top:
        spec = BUILTIN_REGISTRY.get(key)
        if spec:
            result.append({
                "key": key,
                "name": spec.name,
                "description": spec.description,
                "similarity": round(sim, 4),
            })
        else:
            # 非内置工具（MCP/Skill）可能不在 BUILTIN_REGISTRY 中
            result.append({
                "key": key,
                "name": key,
                "description": "",
                "similarity": round(sim, 4),
            })
    return result


async def _enabled_map(session: AsyncSession, user_id: uuid.UUID) -> dict[str, bool]:
    """用户对各内置工具的启停（无记录的用默认值兜底）。"""
    rows = await ToolConfigRepository(session).list_by_user(user_id)
    user_set = {r.tool_key: r.enabled for r in rows}
    result: dict[str, bool] = {}
    for key, spec in BUILTIN_REGISTRY.items():
        result[key] = user_set.get(key, spec.default_enabled)
    return result


async def _build_builtin_tools(
    session: AsyncSession,
    user_id: uuid.UUID,
    citations: list[dict],
    overrides: dict[str, bool] | None,
    stats_holder: dict[str, dict] | None,
    kb_ids: list[str] | None,
) -> list[BaseTool]:
    """只构建内置工具（知识库/记忆/联网/时间），不含 MCP。"""
    overrides = overrides or {}
    enabled = await _enabled_map(session, user_id)
    embed_holder: dict = {}
    stats_holder = stats_holder if stats_holder is not None else {}
    ctx = ToolBuildContext(
        session=session,
        user_id=user_id,
        citations=citations,
        embed_holder=embed_holder,
        stats_holder=stats_holder,
        kb_ids=kb_ids,
    )
    tools: list[BaseTool] = []
    for key, spec in BUILTIN_REGISTRY.items():
        on = overrides.get(key, enabled.get(key, spec.default_enabled))
        if not on:
            continue
        try:
            tool = await spec.builder(ctx)
            if tool is not None:  # needs_config 但未配置时 builder 返回 None
                tools.append(tool)
        except Exception as e:
            logger.warning("构建工具失败（跳过）: %s: %s", key, e)
    return tools


async def build_enabled_tools(
    session: AsyncSession,
    user_id: uuid.UUID,
    citations: list[dict],
    overrides: dict[str, bool] | None = None,
    stats_holder: dict[str, dict] | None = None,
    kb_ids: list[str] | None = None,
    enable_mcp: bool = False,
    mcp_server_ids: list[str] | None = None,
    layered: bool = True,
    agent_callable_personas: list | None = None,
) -> list[BaseTool]:
    """构建用户当前启用的工具列表（内置 + 可选 MCP / Agent-as-Tool）。

    mcp_server_ids: 非空时只加载指定 ID 的 MCP Server（角色级过滤）。
    layered: True=仅返回 layer="core" 的核心工具（扩展工具通过 tool_search 按需发现）；
             False=返回全部工具（旧版全量注入行为）。
    agent_callable_personas: 可被其他角色调用的 AgentPersona 列表（allow_agent_call=True）。
                             对应的 agent 工具写入 embedding 缓存供 tool_search 发现，
                             且仅在 layered=False 时注入 prompt。
    """
    tools = await _build_builtin_tools(
        session, user_id, citations, overrides, stats_holder, kb_ids
    )

    # 预计算核心工具 embedding（layered 与非 layered 模式都计算，确保 tool_search 可查）
    try:
        await _precompute_core_embeddings(session, user_id)
    except Exception as e:
        logger.warning("预计算核心工具 embedding 失败（忽略）: %s", e)

    if enable_mcp and not layered:
        try:
            from app.core.agent.tools.mcp.loader import build_mcp_tools

            mcp_tools = await build_mcp_tools(session, user_id, server_ids=mcp_server_ids)
            tools.extend(mcp_tools)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("构建 MCP 工具失败（忽略）: %s", e)

    # ── Agent-as-Tool 工具 ──────────────────────────────────────────
    if agent_callable_personas:
        try:
            from app.core.agent.tools.builtin.agent_tool import build_agent_tool as _build_at

            agent_tools: list[BaseTool] = []
            at_ctx = ToolBuildContext(
                session=session,
                user_id=user_id,
                citations=citations,
                embed_holder={},
                stats_holder=stats_holder or {},
                kb_ids=kb_ids,
            )
            for persona in agent_callable_personas:
                try:
                    tool = await _build_at(persona, at_ctx)
                    if tool is not None:
                        agent_tools.append(tool)
                        # 注册 embedding 供 tool_search 发现
                        await _compute_and_cache_embedding(
                            tool.name,
                            getattr(persona, "name", tool.name),
                            (tool.description or "")[:300],
                            session, user_id,
                        )
                except Exception as e:
                    logger.warning("构建 agent 工具失败（跳过）: persona=%s err=%s", getattr(persona, "name", "?"), e)

            if not layered:
                tools.extend(agent_tools)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("构建 Agent-as-Tool 工具失败（忽略）: %s", e)
    # ── ──────────────────────────────────────────────────────────────

    # 非 layered 模式过滤掉 layer="core" 之外的工具
    # （layered=True 时，扩展工具如 MCP/Skill 尚未加载，tools 中本就不含它们）
    if not layered:
        # 当 layered=False 时全量返回（旧版行为），无需额外过滤
        pass

    return tools


@asynccontextmanager
async def build_enabled_tools_cm(
    session: AsyncSession,
    user_id: uuid.UUID,
    citations: list[dict],
    overrides: dict[str, bool] | None = None,
    stats_holder: dict[str, dict] | None = None,
    kb_ids: list[str] | None = None,
    layered: bool = True,
    agent_callable_personas: list | None = None,
):
    """构建启用工具（内置 + MCP + Agent-as-Tool）的上下文管理器版本：MCP 走「持久会话」。

    用法：
        async with build_enabled_tools_cm(...) as tools:
            ... 在此期间用 tools 跑工具编排（同一批 MCP 会话整轮复用，不重复握手）...
        # 退出时自动关闭 MCP 会话（正常/异常/取消都清理）

    MCP 模块不可用时，仅产出内置工具。
    layered: True=仅返回 core 层工具（MCP 由 tool_search 发现）；False=全量返回。
    agent_callable_personas: 可调用角色列表，注册 embedding 供 tool_search 发现。
    """
    tools = await _build_builtin_tools(
        session, user_id, citations, overrides, stats_holder, kb_ids
    )
    # ── Agent-as-Tool 工具（仅注册 embedding，layered 时也写入缓存） ──
    if agent_callable_personas:
        try:
            from app.core.agent.tools.builtin.agent_tool import build_agent_tool as _build_at

            at_ctx = ToolBuildContext(
                session=session,
                user_id=user_id,
                citations=citations,
                embed_holder={},
                stats_holder=stats_holder or {},
                kb_ids=kb_ids,
            )
            for persona in agent_callable_personas:
                try:
                    tool = await _build_at(persona, at_ctx)
                    if tool is not None:
                        await _compute_and_cache_embedding(
                            tool.name,
                            getattr(persona, "name", tool.name),
                            (tool.description or "")[:300],
                            session, user_id,
                        )
                        if not layered:
                            tools.append(tool)
                except Exception as e:
                    logger.warning("构建 agent 工具失败（跳过）: persona=%s err=%s", getattr(persona, "name", "?"), e)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("构建 Agent-as-Tool 工具失败（忽略）: %s", e)
    # ── ──────────────────────────────────────────────────────────────

    if layered:
        yield tools
        return

    try:
        from app.core.agent.tools.mcp.loader import open_mcp_tools
    except ImportError:
        yield tools
        return
    async with open_mcp_tools(session, user_id) as mcp_tools:
        yield [*tools, *mcp_tools]


async def list_tools_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> list[dict]:
    """工具配置页用：列出全部内置工具定义 + 用户启停状态。"""
    enabled = await _enabled_map(session, user_id)
    out: list[dict] = []
    for key, spec in BUILTIN_REGISTRY.items():
        out.append({
            "tool_key": key,
            "name": spec.name,
            "description": spec.description,
            "icon": spec.icon,
            "tool_type": "builtin",
            "needs_config": spec.needs_config,
            "config_hint": spec.config_hint,
            "enabled": enabled.get(key, spec.default_enabled),
        })
    return out


__all__ = [
    "build_enabled_tools", "build_enabled_tools_cm", "list_tools_for_user",
    "search_tools", "_TOOL_EMBEDDING_CACHE",
    "_compute_and_cache_embedding", "invalidate_tool_embedding",
]
