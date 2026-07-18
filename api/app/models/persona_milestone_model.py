"""角色成长里程碑 ORM 模型。

里程碑在关键互动节点触发，LLM 生成故事化描述。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class PersonaMilestone(Base):
    __tablename__ = "persona_milestones"
    __table_args__ = (
        UniqueConstraint(
            "persona_id", "user_id", "milestone_type", "occurred_at",
            name="uq_milestone_type_time",
        ),
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

    milestone_type: Mapped[str] = mapped_column(String(32))
    level_at_trigger: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text)
    triggered_by_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    memory_entities: Mapped[list] = mapped_column(JSONB, default=list)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
