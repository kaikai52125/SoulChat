"""角色成长业务服务：互动后记录成长、检测里程碑、解锁特质。

每次对话互动后，由 chat_service 异步调用 record_interaction()。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.persona import milestone_detector as md
from app.core.persona.level_config import (
    DAILY_XP_CAP,
    xp_to_next_level,
)
from app.core.persona.trait_config import get_unlockable_traits
from app.core.persona.xp_engine import (
    calculate_xp_gain,
    check_level_up,
    compute_intimacy,
    update_consecutive_days,
)
from app.models.agent_persona_model import AgentPersona
from app.models.persona_growth_model import PersonaGrowth
from app.repositories.agent_persona_repository import AgentPersonaRepository
from app.repositories.persona_growth_repository import PersonaGrowthRepository

logger = get_logger(__name__)


class PersonaGrowthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = PersonaGrowthRepository(session)

    async def record_interaction(
        self,
        persona_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        conversation_turn_count: int = 1,
        used_old_memory: bool = False,
        used_tools: bool = False,
        emotion_valence: float = 0.0,
        consecutive_high_emotion: int = 0,
    ) -> dict:
        """记录一次互动，更新成长数值、检测里程碑、解锁特质。

        返回: {xp_gained, new_xp, level_before, level_after, did_level_up,
                intimacy, new_milestones, new_traits}
        """
        growth = await self.repo.get_or_create(persona_id, user_id)
        level_before = growth.level

        # ── 连续天数更新 ──
        old_consecutive = growth.consecutive_days
        new_consecutive, _ = update_consecutive_days(
            old_consecutive, growth.last_interaction_at
        )
        is_consecutive_7 = old_consecutive != 7 and new_consecutive >= 7

        # ── XP 计算 ──
        # 检查今日是否已达上限（简化：依赖每日首次调用时的重置逻辑）
        xp_result = calculate_xp_gain(
            conversation_turn_count=conversation_turn_count,
            used_old_memory=used_old_memory,
            used_tools=used_tools,
            emotion_valence=emotion_valence,
            is_consecutive_7=is_consecutive_7,
            is_first_milestone=False,  # 由里程碑检测单独处理
        )

        # 每日上限检查（简化实现：如果今天已互动过，限制 XP）
        today = datetime.now(timezone.utc).date()
        if growth.daily_xp_date != today:
            growth.daily_xp = 0
            growth.daily_xp_date = today
        room = max(DAILY_XP_CAP - growth.daily_xp, 0)
        xp_gained = min(xp_result["total"], room)
        growth.daily_xp += xp_gained

        # ── 更新成长数值 ──
        growth.xp += xp_gained
        growth.interaction_count += 1
        growth.total_tool_calls += 1 if used_tools else 0
        growth.consecutive_days = new_consecutive
        growth.last_interaction_at = datetime.now(timezone.utc)

        # ── 等级更新 ──
        new_level, did_level_up = check_level_up(level_before, growth.xp)
        growth.level = new_level

        # ── 亲密度 ──
        milestone_count = await self.repo.milestone_count(persona_id, user_id)
        growth.intimacy = compute_intimacy(
            level=new_level,
            max_level=50,
            consecutive_days=new_consecutive,
            milestone_count=milestone_count,
            avg_emotion_valence=emotion_valence,
        )

        await self.repo.save(growth)

        # ── 里程碑检测 ──
        new_milestones = []
        persona_repo = AgentPersonaRepository(self.session)
        persona = await persona_repo.get(user_id, persona_id)

        if persona:
            new_milestones = await self._detect_milestones(
                growth, persona,
                conversation_turn_count=conversation_turn_count,
                used_old_memory=used_old_memory,
                consecutive_high_emotion=consecutive_high_emotion,
            )

        # ── 特质解锁 ──
        new_traits = []
        if did_level_up:
            unlocked = get_unlockable_traits(new_level, growth.unlocked_traits)
            for trait in unlocked:
                growth.unlocked_traits = list(growth.unlocked_traits) + [trait["key"]]
                new_traits.append(trait["key"])
            if new_traits:
                await self.repo.save(growth)

        return {
            "xp_gained": xp_gained,
            "new_xp": growth.xp,
            "level_before": level_before,
            "level_after": new_level,
            "did_level_up": did_level_up,
            "intimacy": growth.intimacy,
            "new_milestones": new_milestones,
            "new_traits": new_traits,
        }

    async def _detect_milestones(
        self,
        growth: PersonaGrowth,
        persona: AgentPersona,
        *,
        conversation_turn_count: int,
        used_old_memory: bool,
        consecutive_high_emotion: int,
    ) -> list[dict]:
        """检测并创建新里程碑。"""
        persona_id = growth.persona_id
        user_id = growth.user_id
        new_milestones = []

        # 初次相遇
        if md.check_first_meeting(growth.interaction_count - 1, growth.interaction_count):
            ms = md.build_milestone(
                persona_id, user_id, "first_meeting",
                title="初次相遇",
                description="这是我们的第一次对话，一切都是新的开始。",
                level_at_trigger=growth.level,
            )
            await self.repo.add_milestone(ms)
            new_milestones.append({"type": "first_meeting", "title": ms.title})

        # 深度长谈
        if md.check_deep_talk(conversation_turn_count):
            exists = await self.repo.milestone_exists(persona_id, user_id, "deep_talk")
            if not exists:
                ms = md.build_milestone(
                    persona_id, user_id, "deep_talk",
                    title="深夜长谈",
                    description=f"我们一口气聊了 {conversation_turn_count} 轮，很久没这么畅快了。",
                    level_at_trigger=growth.level,
                )
                await self.repo.add_milestone(ms)
                new_milestones.append({"type": "deep_talk", "title": ms.title})

        # 记忆突破
        if md.check_memory_breakthrough(
            used_old_memory,
            await self.repo.milestone_exists(persona_id, user_id, "memory_breakthrough"),
        ):
            ms = md.build_milestone(
                persona_id, user_id, "memory_breakthrough",
                title="记忆闪光",
                description="今天我第一次真正「记住」了你的过去——那些不是数据，是你的人生。",
                level_at_trigger=growth.level,
            )
            await self.repo.add_milestone(ms)
            new_milestones.append({"type": "memory_breakthrough", "title": ms.title})

        # 情绪峰值
        if md.check_emotion_peak(consecutive_high_emotion):
            ms = md.build_milestone(
                persona_id, user_id, "emotion_peak",
                title="心潮澎湃",
                description="连续感受到了你强烈的情绪波动，我会更用心地倾听。",
                level_at_trigger=growth.level,
            )
            await self.repo.add_milestone(ms)
            new_milestones.append({"type": "emotion_peak", "title": ms.title})

        # 连续互动（7/30/100/365）
        if md.check_loyalty_milestone(growth.consecutive_days):
            ms = md.build_milestone(
                persona_id, user_id, "loyalty_milestone",
                title="不离不弃",
                description=f"我们已经连续互动 {growth.consecutive_days} 天了，谢谢你的信任。",
                level_at_trigger=growth.level,
            )
            await self.repo.add_milestone(ms)
            new_milestones.append(
                {"type": "loyalty_milestone", "days": growth.consecutive_days, "title": ms.title}
            )

        return new_milestones

    async def get_growth(
        self, persona_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict | None:
        """获取成长摘要。"""
        growth = await self.repo.get_by_pair(persona_id, user_id)
        if growth is None:
            return None

        need, total = xp_to_next_level(growth.xp)
        return {
            "xp": growth.xp,
            "level": growth.level,
            "intimacy": growth.intimacy,
            "interaction_count": growth.interaction_count,
            "consecutive_days": growth.consecutive_days,
            "total_tool_calls": growth.total_tool_calls,
            "unlocked_traits": growth.unlocked_traits,
            "xp_to_next": need,
            "xp_total_next": total,
            "xp_progress_pct": round((total - need) / total * 100, 1) if total > 0 else 0,
        }

    async def list_milestones(
        self, persona_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[dict]:
        """获取里程碑列表。"""
        milestones = await self.repo.list_milestones(persona_id, user_id)
        meta = md.MILESTONE_TYPES
        return [
            {
                "id": str(m.id),
                "type": m.milestone_type,
                "type_name": meta.get(m.milestone_type, {}).get("name", m.milestone_type),
                "title": m.title,
                "description": m.description,
                "level_at_trigger": m.level_at_trigger,
                "occurred_at": m.occurred_at.isoformat() if m.occurred_at else None,
            }
            for m in milestones
        ]
