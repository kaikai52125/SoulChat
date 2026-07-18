"""角色成长数据访问层。"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.persona_growth_model import PersonaGrowth
from app.models.persona_milestone_model import PersonaMilestone


async def batch_get_levels(
    session: AsyncSession, persona_ids: list[uuid.UUID], user_id: uuid.UUID
) -> dict[str, dict]:
    """批量获取指定角色的成长摘要。返回 {persona_id_str: {level, xp, intimacy}}。

    一次查询,不做 N+1。
    """
    if not persona_ids:
        return {}
    result = await session.execute(
        select(PersonaGrowth).where(
            PersonaGrowth.persona_id.in_(persona_ids),
            PersonaGrowth.user_id == user_id,
        )
    )
    rows = result.scalars().all()
    return {
        str(r.persona_id): {"level": r.level, "xp": r.xp, "intimacy": r.intimacy}
        for r in rows
    }


class PersonaGrowthRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(
        self, persona_id: uuid.UUID, user_id: uuid.UUID
    ) -> PersonaGrowth:
        """获取或创建成长记录。"""
        result = await self.session.execute(
            select(PersonaGrowth).where(
                PersonaGrowth.persona_id == persona_id,
                PersonaGrowth.user_id == user_id,
            )
        )
        growth = result.scalar_one_or_none()
        if growth is None:
            growth = PersonaGrowth(
                persona_id=persona_id,
                user_id=user_id,
                first_interaction_at=datetime.now(timezone.utc),
            )
            self.session.add(growth)
            await self.session.commit()
            await self.session.refresh(growth)
        return growth

    async def get_by_pair(
        self, persona_id: uuid.UUID, user_id: uuid.UUID
    ) -> PersonaGrowth | None:
        result = await self.session.execute(
            select(PersonaGrowth).where(
                PersonaGrowth.persona_id == persona_id,
                PersonaGrowth.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def save(self, growth: PersonaGrowth) -> PersonaGrowth:
        await self.session.commit()
        await self.session.refresh(growth)
        return growth

    async def add_milestone(self, milestone: PersonaMilestone) -> PersonaMilestone:
        self.session.add(milestone)
        await self.session.commit()
        await self.session.refresh(milestone)
        return milestone

    async def list_milestones(
        self, persona_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[PersonaMilestone]:
        result = await self.session.execute(
            select(PersonaMilestone)
            .where(
                PersonaMilestone.persona_id == persona_id,
                PersonaMilestone.user_id == user_id,
            )
            .order_by(PersonaMilestone.occurred_at.desc())
        )
        return list(result.scalars().all())

    async def milestone_exists(
        self, persona_id: uuid.UUID, user_id: uuid.UUID, milestone_type: str
    ) -> bool:
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count(PersonaMilestone.id)).where(
                PersonaMilestone.persona_id == persona_id,
                PersonaMilestone.user_id == user_id,
                PersonaMilestone.milestone_type == milestone_type,
            )
        )
        return result.scalar_one() > 0

    async def milestone_count(
        self, persona_id: uuid.UUID, user_id: uuid.UUID
    ) -> int:
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count(PersonaMilestone.id)).where(
                PersonaMilestone.persona_id == persona_id,
                PersonaMilestone.user_id == user_id,
            )
        )
        return result.scalar_one() or 0
