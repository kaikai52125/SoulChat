"""角色成长状态 ORM 模型 —— 追踪每个 (角色, 用户) 对的成长数值。

一个角色对一个用户只有一条 growth 记录，随每次互动更新。
"""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class PersonaGrowth(Base):
    __tablename__ = "persona_growth"
    __table_args__ = (
        UniqueConstraint("persona_id", "user_id", name="uq_persona_growth_pair"),
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

    # ── 核心成长数值 ──
    xp: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    intimacy: Mapped[float] = mapped_column(Float, default=0.0)

    # ── 每日 XP 追踪（用于上限检查）──
    daily_xp: Mapped[int] = mapped_column(Integer, default=0)  # 今日已获得 XP
    daily_xp_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # daily_xp 对应的日期

    # ── 累计统计 ──
    interaction_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens_exchanged: Mapped[int] = mapped_column(BigInteger, default=0)
    total_tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_days: Mapped[int] = mapped_column(Integer, default=0)
    last_interaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_interaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── 解锁状态 ──
    unlocked_traits: Mapped[list] = mapped_column(JSONB, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
