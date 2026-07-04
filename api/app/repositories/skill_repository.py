"""技能数据访问层。技能归属于 Persona（角色），按 persona_id 隔离。"""
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill_model import Skill


class SkillRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_persona(self, persona_id: uuid.UUID) -> list[Skill]:
        result = await self.session.execute(
            select(Skill)
            .where(Skill.persona_id == persona_id)
            .order_by(Skill.sort, Skill.created_at)
        )
        return list(result.scalars().all())

    async def get(self, persona_id: uuid.UUID, skill_id: uuid.UUID) -> Skill | None:
        result = await self.session.execute(
            select(Skill).where(
                Skill.id == skill_id, Skill.persona_id == persona_id
            )
        )
        return result.scalar_one_or_none()

    async def get_any(self, skill_id: uuid.UUID) -> Skill | None:
        """跨角色查询单个技能（市场 fork 等场景）。"""
        result = await self.session.execute(
            select(Skill).where(Skill.id == skill_id)
        )
        return result.scalar_one_or_none()

    async def get_by_ids(
        self, persona_id: uuid.UUID, skill_ids: list[uuid.UUID]
    ) -> list[Skill]:
        if not skill_ids:
            return []
        result = await self.session.execute(
            select(Skill).where(
                Skill.id.in_(skill_ids), Skill.persona_id == persona_id
            )
        )
        return list(result.scalars().all())

    async def count(self, persona_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(Skill.id).where(Skill.persona_id == persona_id)
        )
        return len(result.all())

    async def get_by_import_hash(
        self, persona_id: uuid.UUID, import_hash: str
    ) -> Skill | None:
        if not import_hash:
            return None
        result = await self.session.execute(
            select(Skill).where(
                Skill.persona_id == persona_id,
                Skill.import_hash == import_hash,
            )
        )
        return result.scalars().first()

    # ── 技能市场 ──

    async def list_public(self, limit: int = 50, offset: int = 0) -> list[Skill]:
        """公开技能列表（市场），按调用次数倒序。"""
        result = await self.session.execute(
            select(Skill)
            .where(Skill.is_public.is_(True))
            .order_by(Skill.call_count.desc(), Skill.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    # ── 调用计数 ──

    async def bump_call_count(self, skill_id: uuid.UUID) -> None:
        """技能被调用时 call_count +1。"""
        await self.session.execute(
            update(Skill)
            .where(Skill.id == skill_id)
            .values(call_count=Skill.call_count + 1)
        )
        await self.session.commit()

    # ── CRUD ──

    async def add(self, skill: Skill) -> Skill:
        self.session.add(skill)
        await self.session.commit()
        await self.session.refresh(skill)
        return skill

    async def save(self, skill: Skill) -> Skill:
        await self.session.commit()
        await self.session.refresh(skill)
        return skill

    async def delete(self, skill: Skill) -> None:
        await self.session.delete(skill)
        await self.session.commit()
