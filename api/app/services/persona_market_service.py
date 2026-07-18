"""角色市场业务服务：发布、浏览、导入、评价。"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.logging import get_logger
from app.models.agent_persona_model import AgentPersona
from app.models.persona_market_models import MarketListing, MarketReview
from app.repositories.agent_persona_repository import AgentPersonaRepository
from app.repositories.persona_market_repository import PersonaMarketRepository

logger = get_logger(__name__)


def _make_snapshot(persona: AgentPersona) -> dict:
    """生成角色配置的完整快照。"""
    return {
        "system_prompt": persona.system_prompt,
        "temperature": persona.temperature,
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


class PersonaMarketService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = PersonaMarketRepository(session)
        self.persona_repo = AgentPersonaRepository(session)

    async def publish(
        self, persona_id: uuid.UUID, user_id: uuid.UUID,
        market_name: str, market_description: str,
        tags: list[str], icon: str,
    ) -> MarketListing:
        """发布角色到市场。"""
        persona = await self.persona_repo.get(user_id, persona_id)
        if persona is None:
            raise BizError("角色不存在", code=4040, status_code=404)

        snap = _make_snapshot(persona)
        # 把角色关联的技能也打包进快照
        from app.models.skill_model import Skill
        from sqlalchemy import select
        skill_result = await self.session.execute(
            select(Skill).where(Skill.persona_id == persona_id)
        )
        skills = skill_result.scalars().all()
        snap["skills"] = [
            {"name": s.name, "description": s.description, "icon": s.icon,
             "prompt": s.prompt, "tool_keys": s.tool_keys, "config": s.config}
            for s in skills
        ]
        # MCP 服务器详情（名字+URL），帮助导入者了解需要哪些 MCP
        mcp_ids = persona.mcp_server_ids or []
        if mcp_ids:
            from app.models.mcp_server_model import MCPServer
            mcp_result = await self.session.execute(
                select(MCPServer.id, MCPServer.name, MCPServer.url).where(MCPServer.id.in_(mcp_ids))
            )
            snap["mcp_servers"] = [{"id": str(r[0]), "name": r[1], "url": r[2]} for r in mcp_result.all()]

        existing = await self.repo.get_by_persona(persona_id)
        if existing:
            existing.market_name = market_name
            existing.market_description = market_description
            existing.tags = tags
            existing.icon = icon
            existing.persona_snapshot = snap
            existing.is_active = True
            persona.is_listed = True
            await self.repo.save(existing)
            await self.persona_repo.save(persona)
            return existing

        listing = MarketListing(
            persona_id=persona_id,
            seller_user_id=user_id,
            market_name=market_name,
            market_description=market_description,
            tags=tags,
            icon=icon,
            persona_snapshot=snap,
        )
        persona.is_listed = True
        await self.repo.create_listing(listing)
        await self.persona_repo.save(persona)
        return listing

    async def unpublish(self, listing_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """下架市场挂牌。"""
        listing = await self.repo.get_by_id(listing_id)
        if listing is None:
            raise BizError("挂牌不存在", code=4040, status_code=404)
        if listing.seller_user_id != user_id:
            raise BizError("无权操作", code=4030, status_code=403)

        listing.is_active = False
        persona = await self.persona_repo.get(user_id, listing.persona_id)
        if persona:
            persona.is_listed = False
            await self.persona_repo.save(persona)
        await self.repo.save(listing)

    async def list_marketplace(
        self,
        tags: list[str] | None = None,
        sort: str = "popular",
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """浏览市场。"""
        items, total = await self.repo.list_active(
            tags=tags, sort=sort, search=search, page=page, page_size=page_size
        )
        cards = []
        for item in items:
            snap = item.persona_snapshot or {}
            cards.append({
                "id": str(item.id),
                "persona_id": str(item.persona_id),
                "market_name": item.market_name,
                "market_description": item.market_description,
                "tags": item.tags or [],
                "icon": item.icon,
                "downloads": item.downloads,
                "rating_avg": item.rating_avg,
                "rating_count": item.rating_count,
                "version": item.version,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "skills": snap.get("skills") or [],
                "mcp_servers": snap.get("mcp_servers") or [],
            })
        return cards, total

    async def get_detail(self, listing_id: uuid.UUID) -> dict | None:
        """获取挂牌详情（含评价+评价者昵称）。"""
        listing = await self.repo.get_by_id(listing_id)
        if listing is None or not listing.is_active:
            return None
        reviews = await self.repo.get_reviews(listing_id)
        # 批量查用户名
        reviewer_ids = list({r.user_id for r in reviews})
        user_names: dict[str, str] = {}
        if reviewer_ids:
            from app.models.user_model import User
            from sqlalchemy import select
            user_result = await self.session.execute(
                select(User.id, User.nickname).where(User.id.in_(reviewer_ids))
            )
            user_names = {str(uid): (nickname or str(uid)[:8]) for uid, nickname in user_result.all()}
        return {
            "id": str(listing.id),
            "persona_id": str(listing.persona_id),
            "seller_user_id": str(listing.seller_user_id),
            "market_name": listing.market_name,
            "market_description": listing.market_description,
            "tags": listing.tags or [],
            "icon": listing.icon,
            "persona_snapshot": {
                "system_prompt": listing.persona_snapshot.get("system_prompt", "")[:300],
                "skills": listing.persona_snapshot.get("skills") or [],
                "mcp_servers": listing.persona_snapshot.get("mcp_servers") or [],
            },
            "downloads": listing.downloads,
            "rating_avg": listing.rating_avg,
            "rating_count": listing.rating_count,
            "version": listing.version,
            "changelog": listing.changelog,
            "created_at": listing.created_at.isoformat() if listing.created_at else None,
            "reviews": [
                {
                    "id": str(r.id),
                    "user_id": str(r.user_id),
                    "user_name": user_names.get(str(r.user_id), "匿名用户"),
                    "rating": r.rating,
                    "comment": r.comment,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in reviews
            ],
        }

    async def import_persona(
        self, listing_id: uuid.UUID, target_user_id: uuid.UUID
    ) -> AgentPersona:
        """从市场导入角色到用户列表。"""
        listing = await self.repo.get_by_id(listing_id)
        if listing is None or not listing.is_active:
            raise BizError("挂牌不存在或已下架", code=4040, status_code=404)
        if listing.seller_user_id == target_user_id:
            raise BizError("不能导入自己的角色", code=4000, status_code=400)

        snap = listing.persona_snapshot
        persona = AgentPersona(
            user_id=target_user_id,
            name=listing.market_name,
            system_prompt=snap.get("system_prompt", ""),
            temperature=snap.get("temperature", 0.7),
            tool_keys=snap.get("tool_keys", []),
            enable_knowledge=snap.get("enable_knowledge", True),
            enable_memory=snap.get("enable_memory", True),
            enable_web_search=snap.get("enable_web_search", False),
            enable_mcp=snap.get("enable_mcp", False),
            mcp_server_ids=[],  # MCP 服务器是用户级别配置，导入后需自行配置
            enable_active_recall=snap.get("enable_active_recall", True),
            enable_cross_session=snap.get("enable_cross_session", False),
            kb_ids=snap.get("kb_ids", []),
            conversation_scope=snap.get("conversation_scope", "shared"),
            context_window=snap.get("context_window", 20),
            human_mode=snap.get("human_mode", False),
            show_avatar=snap.get("show_avatar", False),
            allow_agent_call=snap.get("allow_agent_call", False),
            cloned_from_id=listing.persona_id,
        )
        created = await self.persona_repo.add(persona)

        # 复制技能
        skill_data = snap.get("skills") or []
        if skill_data:
            from app.models.skill_model import Skill
            from app.repositories.skill_repository import SkillRepository
            skill_repo = SkillRepository(self.session)
            for sd in skill_data:
                skill = Skill(
                    persona_id=created.id,
                    name=sd.get("name", ""),
                    description=sd.get("description", ""),
                    icon=sd.get("icon", "🧩"),
                    prompt=sd.get("prompt", ""),
                    tool_keys=sd.get("tool_keys", []),
                    config=sd.get("config", {}),
                    source="marketplace",
                )
                self.session.add(skill)
            await self.session.commit()

        # 更新统计
        await self.repo.increment_downloads(listing_id)
        seller_persona = await self.persona_repo.get(
            listing.seller_user_id, listing.persona_id
        )
        if seller_persona:
            seller_persona.clone_count = (seller_persona.clone_count or 0) + 1
            await self.persona_repo.save(seller_persona)

        # 为新导入的角色创建初始成长记录
        from app.repositories.persona_growth_repository import PersonaGrowthRepository
        growth_repo = PersonaGrowthRepository(self.session)
        await growth_repo.get_or_create(created.id, target_user_id)

        return created

    async def add_review(
        self, listing_id: uuid.UUID, user_id: uuid.UUID,
        rating: int, comment: str | None,
    ) -> MarketReview:
        """添加或更新评价。"""
        listing = await self.repo.get_by_id(listing_id)
        if listing is None:
            raise BizError("挂牌不存在", code=4040, status_code=404)

        review = MarketReview(
            listing_id=listing_id,
            user_id=user_id,
            rating=rating,
            comment=comment,
        )
        return await self.repo.upsert_review(review)
