"""角色日记数据访问层。"""
import uuid
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.persona_diary_model import PersonaDiary


class PersonaDiaryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        persona_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PersonaDiary], int]:
        """分页列出用户的日记，可选按角色筛选。"""
        stmt = select(PersonaDiary).where(PersonaDiary.user_id == user_id)
        count_stmt = select(func.count(PersonaDiary.id)).where(
            PersonaDiary.user_id == user_id
        )

        if persona_id is not None:
            stmt = stmt.where(PersonaDiary.persona_id == persona_id)
            count_stmt = count_stmt.where(PersonaDiary.persona_id == persona_id)

        stmt = stmt.order_by(PersonaDiary.diary_date.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar_one()

        return items, total

    async def get_by_id(self, diary_id: uuid.UUID) -> PersonaDiary | None:
        result = await self.session.execute(
            select(PersonaDiary).where(PersonaDiary.id == diary_id)
        )
        return result.scalar_one_or_none()

    async def mark_read(self, diary_id: uuid.UUID) -> None:
        await self.session.execute(
            update(PersonaDiary)
            .where(PersonaDiary.id == diary_id)
            .values(is_read=True)
        )
        await self.session.commit()

    async def get_unread_count(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count(PersonaDiary.id)).where(
                PersonaDiary.user_id == user_id,
                PersonaDiary.is_read == False,  # noqa: E712
            )
        )
        return result.scalar_one() or 0

    async def exists_for_date(
        self, persona_id: uuid.UUID, user_id: uuid.UUID, diary_date: date
    ) -> bool:
        result = await self.session.execute(
            select(func.count(PersonaDiary.id)).where(
                PersonaDiary.persona_id == persona_id,
                PersonaDiary.user_id == user_id,
                PersonaDiary.diary_date == diary_date,
            )
        )
        return result.scalar_one() > 0

    async def create(self, diary: PersonaDiary) -> PersonaDiary:
        self.session.add(diary)
        await self.session.commit()
        await self.session.refresh(diary)
        return diary
