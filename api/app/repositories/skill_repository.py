"""技能数据访问层。技能归属于 Persona（角色），按 persona_id 隔离。"""
import uuid

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill_model import Skill, SkillCallLog


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

    async def record_call(
        self,
        skill_id: uuid.UUID,
        *,
        success: bool = True,
        tool_name: str = "",
        duration_ms: int = 0,
        error_msg: str | None = None,
    ) -> None:
        """记录一次技能调用：更新计数 + 写调用日志。"""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        vals: dict = {
            "call_count": Skill.call_count + 1,
            "last_called_at": now,
        }
        if success:
            vals["success_count"] = Skill.success_count + 1
        else:
            vals["error_count"] = Skill.error_count + 1

        await self.session.execute(
            update(Skill).where(Skill.id == skill_id).values(**vals)
        )
        self.session.add(
            SkillCallLog(
                skill_id=skill_id,
                tool_name=tool_name,
                success=success,
                duration_ms=duration_ms,
                error_msg=error_msg,
                created_at=now,
            )
        )
        await self.session.commit()

    # ── 调用统计 ──

    async def get_call_stats(self, skill_id: uuid.UUID) -> dict:
        """查询技能的调用统计数据：汇总（从 Skill 表读，含历史）+ 近 30 天每日 + 最近 20 条。"""
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        # Skill 表汇总（含日志表创建前的历史数据）
        skill_row = await self.session.execute(
            select(
                Skill.call_count, Skill.success_count, Skill.error_count,
                Skill.last_called_at,
            ).where(Skill.id == skill_id)
        )
        sk = skill_row.one_or_none()
        if sk is None:
            return {"summary": {"total": 0, "success": 0, "error": 0, "avg_duration_ms": 0}, "daily": [], "recent": []}

        total, success, error, last_called = sk

        # 每日统计（仅日志表）
        daily_rows = await self.session.execute(
            select(
                func.date(SkillCallLog.created_at).label("date"),
                func.count().label("total"),
                func.sum(
                    case((SkillCallLog.success.is_(True), 1), else_=0)
                ).label("success"),
                func.sum(
                    case((SkillCallLog.success.is_(False), 1), else_=0)
                ).label("error"),
            )
            .where(
                SkillCallLog.skill_id == skill_id,
                SkillCallLog.created_at >= thirty_days_ago,
            )
            .group_by(func.date(SkillCallLog.created_at))
            .order_by(func.date(SkillCallLog.created_at))
        )
        daily = [
            {"date": str(r.date), "total": r.total, "success": r.success,
             "error": r.error}
            for r in daily_rows.all()
        ]

        # 最近调用
        recent_rows = await self.session.execute(
            select(SkillCallLog)
            .where(SkillCallLog.skill_id == skill_id)
            .order_by(SkillCallLog.created_at.desc())
            .limit(20)
        )
        recent = [
            {
                "tool_name": r.tool_name,
                "success": r.success,
                "duration_ms": r.duration_ms,
                "error_msg": r.error_msg,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent_rows.scalars().all()
        ]

        avg_ms = 0
        if recent:
            durations = [r["duration_ms"] for r in recent if r["duration_ms"] > 0]
            if durations:
                avg_ms = sum(durations) // len(durations)

        return {
            "summary": {
                "total": total or 0,
                "success": success or 0,
                "error": error or 0,
                "avg_duration_ms": avg_ms,
            },
            "daily": daily,
            "recent": recent,
        }

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
