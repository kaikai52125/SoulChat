"""角色日记 ORM 模型。

每天每个有互动的角色自动生成一篇第一人称日记。
"""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class PersonaDiary(Base):
    __tablename__ = "persona_diaries"
    __table_args__ = (
        UniqueConstraint("persona_id", "user_id", "diary_date", name="uq_diary_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    persona_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_personas.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    diary_date: Mapped[date] = mapped_column(Date)
    content: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mood: Mapped[str | None] = mapped_column(String(16), nullable=True)
    key_topics: Mapped[list] = mapped_column(JSONB, default=list)
    key_insights: Mapped[list] = mapped_column(JSONB, default=list)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
