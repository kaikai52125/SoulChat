"""角色日记路由。"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.services.persona_diary_service import PersonaDiaryService

router = APIRouter(prefix="/diaries", tags=["persona-diary"])


@router.get("")
async def list_diaries(
    persona_id: uuid.UUID | None = Query(None, description="按角色筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """获取日记列表，按日期倒序。"""
    svc = PersonaDiaryService(session)
    items, total = await svc.list_diaries(
        user.id, persona_id=persona_id, page=page, page_size=page_size
    )
    return success({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/unread-count")
async def unread_count(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """获取未读日记数量。"""
    svc = PersonaDiaryService(session)
    count = await svc.get_unread_count(user.id)
    return success({"count": count})


@router.put("/{diary_id}/read")
async def mark_read(
    diary_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """标记日记为已读。"""
    svc = PersonaDiaryService(session)
    await svc.mark_read(diary_id)
    return success(message="已标记")
