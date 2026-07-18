"""角色市场数据访问层。"""
import uuid

from sqlalchemy import func, select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.persona_market_models import MarketListing, MarketReview


class PersonaMarketRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── 挂牌 CRUD ──

    async def list_active(
        self,
        tags: list[str] | None = None,
        sort: str = "popular",
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[MarketListing], int]:
        """分页列出活跃的市场挂牌。"""
        stmt = select(MarketListing).where(MarketListing.is_active == True)  # noqa: E712
        count_stmt = select(func.count(MarketListing.id)).where(
            MarketListing.is_active == True  # noqa: E712
        )

        if tags:
            for tag in tags:
                stmt = stmt.where(MarketListing.tags.contains([tag]))
                count_stmt = count_stmt.where(MarketListing.tags.contains([tag]))

        if search:
            search_filter = or_(
                MarketListing.market_name.ilike(f"%{search}%"),
                MarketListing.market_description.ilike(f"%{search}%"),
            )
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        if sort == "popular":
            stmt = stmt.order_by(MarketListing.downloads.desc())
        elif sort == "rating":
            stmt = stmt.order_by(MarketListing.rating_avg.desc())
        else:  # newest
            stmt = stmt.order_by(MarketListing.created_at.desc())

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar_one()

        return items, total

    async def get_by_id(self, listing_id: uuid.UUID) -> MarketListing | None:
        result = await self.session.execute(
            select(MarketListing).where(MarketListing.id == listing_id)
        )
        return result.scalar_one_or_none()

    async def get_by_persona(self, persona_id: uuid.UUID) -> MarketListing | None:
        result = await self.session.execute(
            select(MarketListing).where(MarketListing.persona_id == persona_id)
        )
        return result.scalar_one_or_none()

    async def create_listing(self, listing: MarketListing) -> MarketListing:
        self.session.add(listing)
        await self.session.commit()
        await self.session.refresh(listing)
        return listing

    async def save(self, listing: MarketListing) -> MarketListing:
        await self.session.commit()
        await self.session.refresh(listing)
        return listing

    async def increment_downloads(self, listing_id: uuid.UUID) -> None:
        await self.session.execute(
            update(MarketListing)
            .where(MarketListing.id == listing_id)
            .values(downloads=MarketListing.downloads + 1)
        )
        await self.session.commit()

    # ── 评价 CRUD ──

    async def get_reviews(
        self, listing_id: uuid.UUID, limit: int = 10
    ) -> list[MarketReview]:
        result = await self.session.execute(
            select(MarketReview)
            .where(MarketReview.listing_id == listing_id)
            .order_by(MarketReview.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_user_review(
        self, listing_id: uuid.UUID, user_id: uuid.UUID
    ) -> MarketReview | None:
        result = await self.session.execute(
            select(MarketReview).where(
                MarketReview.listing_id == listing_id,
                MarketReview.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_review(self, review: MarketReview) -> MarketReview:
        """插入或更新评价，并重算 listing 的评分。"""
        existing = await self.get_user_review(review.listing_id, review.user_id)
        if existing:
            existing.rating = review.rating
            existing.comment = review.comment
        else:
            self.session.add(review)
        await self.session.commit()

        # 重算平均评分
        result = await self.session.execute(
            select(
                func.count(MarketReview.id),
                func.coalesce(func.avg(MarketReview.rating), 0.0),
            ).where(MarketReview.listing_id == review.listing_id)
        )
        cnt, avg = result.one()
        await self.session.execute(
            update(MarketListing)
            .where(MarketListing.id == review.listing_id)
            .values(rating_count=cnt, rating_avg=round(float(avg), 2))
        )
        await self.session.commit()
        await self.session.refresh(existing or review)
        return existing or review
