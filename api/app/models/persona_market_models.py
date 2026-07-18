"""角色市场 ORM 模型：挂牌 + 评价。"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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


class MarketListing(Base):
    __tablename__ = "persona_market_listings"
    __table_args__ = (
        UniqueConstraint("persona_id", name="uq_market_persona"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    persona_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_personas.id", ondelete="CASCADE"),
        index=True,
    )
    seller_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
    )

    market_name: Mapped[str] = mapped_column(String(64))
    market_description: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    icon: Mapped[str] = mapped_column(String(8), default="🤖")

    persona_snapshot: Mapped[dict] = mapped_column(JSONB)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    downloads: Mapped[int] = mapped_column(Integer, default=0)
    rating_avg: Mapped[float] = mapped_column(Float, default=0.0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[str] = mapped_column(String(16), default="1.0")
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MarketReview(Base):
    __tablename__ = "persona_market_reviews"
    __table_args__ = (
        UniqueConstraint("listing_id", "user_id", name="uq_review_user"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persona_market_listings.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
    )

    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
