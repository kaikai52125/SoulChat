"""角色日记业务服务：列表、详情、已读管理。"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.persona_diary_repository import PersonaDiaryRepository


class PersonaDiaryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = PersonaDiaryRepository(session)

    async def list_diaries(
        self,
        user_id: uuid.UUID,
        persona_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """分页列出日记。"""
        items, total = await self.repo.list_by_user(
            user_id, persona_id=persona_id, page=page, page_size=page_size
        )
        return [
            {
                "id": str(d.id),
                "persona_id": str(d.persona_id),
                "diary_date": d.diary_date.isoformat() if d.diary_date else None,
                "title": d.title,
                "content": d.content,
                "mood": d.mood,
                "key_topics": d.key_topics or [],
                "word_count": d.word_count,
                "is_read": d.is_read,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in items
        ], total

    async def get_diary(self, diary_id: uuid.UUID) -> dict | None:
        d = await self.repo.get_by_id(diary_id)
        if d is None:
            return None
        return {
            "id": str(d.id),
            "persona_id": str(d.persona_id),
            "diary_date": d.diary_date.isoformat() if d.diary_date else None,
            "title": d.title,
            "content": d.content,
            "mood": d.mood,
            "key_topics": d.key_topics or [],
            "word_count": d.word_count,
            "is_read": d.is_read,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }

    async def mark_read(self, diary_id: uuid.UUID) -> None:
        await self.repo.mark_read(diary_id)

    async def get_unread_count(self, user_id: uuid.UUID) -> int:
        return await self.repo.get_unread_count(user_id)
