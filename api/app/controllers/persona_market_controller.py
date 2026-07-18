"""角色市场路由：浏览（无需认证）、导入/评价（需认证）、发布/下架（卖家操作）。"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.persona_market_schema import PublishRequest, ReviewRequest, UpdateListingRequest
from app.services.persona_market_service import PersonaMarketService

router = APIRouter(prefix="/personas", tags=["persona-marketplace"])

# ── 全局浏览（无需认证） ──
marketplace_router = APIRouter(prefix="/personas/marketplace", tags=["persona-marketplace"])


@marketplace_router.get("")
async def list_marketplace(
    tag: list[str] = Query(default=[]),
    sort: str = Query("popular", regex="^(popular|newest|rating)$"),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """浏览角色市场。"""
    svc = PersonaMarketService(session)
    items, total = await svc.list_marketplace(
        tags=tag if tag else None,
        sort=sort,
        search=search,
        page=page,
        page_size=page_size,
    )
    return success({"items": items, "total": total, "page": page, "page_size": page_size})


@marketplace_router.get("/{listing_id}")
async def get_detail(
    listing_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """查看挂牌详情。"""
    svc = PersonaMarketService(session)
    data = await svc.get_detail(listing_id)
    if data is None:
        from app.core.exceptions import BizError
        raise BizError("挂牌不存在或已下架", code=4040, status_code=404)
    return success(data)


@marketplace_router.post("/{listing_id}/import")
async def import_persona(
    listing_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """导入角色到我的列表。"""
    from app.services.agent_persona_service import AgentPersonaService

    svc = PersonaMarketService(session)
    persona = await svc.import_persona(listing_id, user.id)
    return success(AgentPersonaService.to_out_dict(persona), "已添加到你的角色列表")


@marketplace_router.post("/{listing_id}/reviews")
async def add_review(
    listing_id: uuid.UUID,
    body: ReviewRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """评价一个市场角色。"""
    svc = PersonaMarketService(session)
    review = await svc.add_review(listing_id, user.id, body.rating, body.comment)
    return success({"id": str(review.id), "rating": review.rating}, "评价已提交")


# ── 卖家操作 ──

@router.post("/{persona_id}/publish")
async def publish_persona(
    persona_id: uuid.UUID,
    body: PublishRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """发布角色到市场。"""
    svc = PersonaMarketService(session)
    listing = await svc.publish(
        persona_id, user.id,
        body.market_name, body.market_description,
        body.tags, body.icon,
    )
    return success({"listing_id": str(listing.id)}, "已发布到市场")


@marketplace_router.put("/{listing_id}")
async def update_listing(
    listing_id: uuid.UUID,
    body: UpdateListingRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """更新市场挂牌信息。"""
    svc = PersonaMarketService(session)
    listing = await svc.repo.get_by_id(listing_id)
    if listing is None or listing.seller_user_id != user.id:
        from app.core.exceptions import BizError
        raise BizError("无权操作", code=4030, status_code=403)

    if body.market_name is not None:
        listing.market_name = body.market_name
    if body.market_description is not None:
        listing.market_description = body.market_description
    if body.tags is not None:
        listing.tags = body.tags
    if body.icon is not None:
        listing.icon = body.icon
    if body.changelog is not None:
        listing.changelog = body.changelog
    await svc.repo.save(listing)
    return success(message="已更新")


@marketplace_router.post("/{listing_id}/unpublish")
async def unpublish_listing(
    listing_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """下架市场挂牌。"""
    svc = PersonaMarketService(session)
    await svc.unpublish(listing_id, user.id)
    return success(message="已下架")
