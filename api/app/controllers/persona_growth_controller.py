"""角色成长路由：获取成长状态和里程碑列表。"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.exceptions import BizError
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.repositories.agent_persona_repository import AgentPersonaRepository
from app.services.persona_growth_service import PersonaGrowthService

router = APIRouter(prefix="/personas", tags=["persona-growth"])


async def _check_persona(user_id: uuid.UUID, persona_id: uuid.UUID, session: AsyncSession):
    persona = await AgentPersonaRepository(session).get(user_id, persona_id)
    if persona is None:
        raise BizError("角色不存在", code=4040, status_code=404)
    return persona


@router.get("/{persona_id}/growth")
async def get_growth(
    persona_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """获取角色成长状态：XP、等级、亲密度、解锁特质等。无记录时自动创建默认记录。"""
    await _check_persona(user.id, persona_id, session)
    from app.repositories.persona_growth_repository import PersonaGrowthRepository
    repo = PersonaGrowthRepository(session)
    # 自动初始化：无记录时创建一个初始记录
    growth = await repo.get_by_pair(persona_id, user.id)
    if growth is None:
        growth = await repo.get_or_create(persona_id, user.id)

    from app.core.persona.level_config import xp_to_next_level
    need, total = xp_to_next_level(growth.xp)
    return success({
        "xp": growth.xp,
        "level": growth.level,
        "intimacy": growth.intimacy,
        "interaction_count": growth.interaction_count,
        "consecutive_days": growth.consecutive_days,
        "total_tool_calls": growth.total_tool_calls,
        "unlocked_traits": growth.unlocked_traits or [],
        "xp_to_next": need,
        "xp_total_next": total,
        "xp_progress_pct": round((total - need) / total * 100, 1) if total > 0 else 0,
    })


@router.get("/{persona_id}/milestones")
async def list_milestones(
    persona_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """获取角色里程碑列表。"""
    await _check_persona(user.id, persona_id, session)
    svc = PersonaGrowthService(session)
    items = await svc.list_milestones(persona_id, user.id)
    return success(items)
