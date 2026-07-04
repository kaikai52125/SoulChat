"""技能（Skill）路由：归属于 Persona + 技能市场 + fork。"""
import uuid

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.exceptions import BizError
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.repositories.agent_persona_repository import AgentPersonaRepository
from app.schemas.skill_schema import SkillCreate, SkillUpdate
from app.services.skill_service import SkillService

# 角色内技能路由
persona_skill_router = APIRouter(
    prefix="/personas/{persona_id}/skills", tags=["skill"]
)

# 技能市场路由（全局）
marketplace_router = APIRouter(prefix="/skills/marketplace", tags=["skill-marketplace"])


async def _check_persona(
    user_id: uuid.UUID, persona_id: uuid.UUID, session: AsyncSession
):
    persona = await AgentPersonaRepository(session).get(user_id, persona_id)
    if persona is None:
        raise BizError("角色不存在", code=4040, status_code=404)
    return persona


# ── 角色内技能 CRUD ──

@persona_skill_router.get("")
async def list_skills(
    persona_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _check_persona(user.id, persona_id, session)
    items = await SkillService(session).list(persona_id)
    return success([SkillService.to_out_dict(s) for s in items])


@persona_skill_router.get("/builtins")
async def list_builtin_skills(persona_id: uuid.UUID, user: User = Depends(get_current_user)):
    return success(SkillService.list_builtins())


@persona_skill_router.post("")
async def create_skill(
    persona_id: uuid.UUID,
    body: SkillCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _check_persona(user.id, persona_id, session)
    skill = await SkillService(session).create(persona_id, user.id, body)
    return success(SkillService.to_out_dict(skill), "已创建")


@persona_skill_router.post("/builtins/{key}")
async def add_builtin_skill(
    persona_id: uuid.UUID,
    key: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _check_persona(user.id, persona_id, session)
    skill = await SkillService(session).add_builtin(persona_id, key)
    return success(SkillService.to_out_dict(skill), "已添加")


@persona_skill_router.post("/import")
async def import_skill(
    persona_id: uuid.UUID,
    file: UploadFile,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _check_persona(user.id, persona_id, session)
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise BizError("请上传 .zip 格式的压缩包", code=4071)
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise BizError("压缩包不能超过 5MB", code=4072)
    skill, existing = await SkillService(session).import_zip(persona_id, user.id, data)
    return success(
        SkillService.to_out_dict(skill),
        "该技能已存在，无需重复导入" if existing else "已导入",
    )


@persona_skill_router.put("/{skill_id}")
async def update_skill(
    persona_id: uuid.UUID,
    skill_id: uuid.UUID,
    body: SkillUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _check_persona(user.id, persona_id, session)
    skill = await SkillService(session).update(persona_id, user.id, skill_id, body)
    return success(SkillService.to_out_dict(skill), "已保存")


@persona_skill_router.delete("/{skill_id}")
async def delete_skill(
    persona_id: uuid.UUID,
    skill_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _check_persona(user.id, persona_id, session)
    await SkillService(session).delete(persona_id, skill_id)
    return success(message="已删除")


# ── 技能市场 ──

@marketplace_router.get("")
async def list_marketplace(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    items = await SkillService(session).list_marketplace(limit=limit, offset=offset)
    return success([SkillService.to_out_dict(s) for s in items])


@marketplace_router.post("/{skill_id}/fork")
async def fork_skill(
    skill_id: uuid.UUID,
    persona_id: uuid.UUID = Query(..., description="目标角色 ID"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """从市场复制技能到指定角色。"""
    await _check_persona(user.id, persona_id, session)
    skill = await SkillService(session).fork(persona_id, user.id, skill_id)
    return success(SkillService.to_out_dict(skill), "已添加到角色")
