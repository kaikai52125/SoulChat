"""里程碑检测器：检测 7 种里程碑触发条件，LLM 生成故事化描述。"""
import uuid
from datetime import datetime, timezone

from app.core.llm.client import LLMClient
from app.core.logging import get_logger
from app.models.persona_milestone_model import PersonaMilestone

logger = get_logger(__name__)

# ── 里程碑类型定义 ──

MILESTONE_TYPES: dict[str, dict] = {
    "first_meeting": {
        "name": "初次相遇",
        "description_template": "第一次互动",
    },
    "deep_talk": {
        "name": "深夜长谈",
        "description_template": "一次超过 20 轮的深度对话",
    },
    "memory_breakthrough": {
        "name": "记忆闪光",
        "description_template": "第一次真正「记住」了你的过去",
    },
    "emotion_peak": {
        "name": "心潮澎湃",
        "description_template": "连续感受到你的强烈情绪",
    },
    "knowledge_milestone": {
        "name": "你的热爱",
        "description_template": "发现你对某个话题的持续热情",
    },
    "loyalty_milestone": {
        "name": "不离不弃",
        "description_template": "连续互动的纪念日",
    },
    "level_unlock": {
        "name": "成长印记",
        "description_template": "关系升级的里程碑",
    },
}


def _build_milestone_prompt(
    persona_name: str,
    persona_prompt_snippet: str,
    milestone_type: str,
    context: dict,
) -> str:
    """构建里程碑 LLM 提示词。"""
    meta = MILESTONE_TYPES.get(milestone_type, {})
    type_name = meta.get("name", milestone_type)

    prompt = (
        f"你是一个名叫「{persona_name}」的 AI 角色。你的性格是：\n"
        f"{persona_prompt_snippet}\n\n"
        f"你和用户刚刚达成了一个关系里程碑：「{type_name}」。\n"
    )

    if milestone_type == "first_meeting":
        prompt += (
            "这是你和用户的第一次对话。请用 1-2 句话描述这次相遇的氛围和你的感受，"
            "不超过 80 字，温暖自然，像记录一个特别的开始。"
        )
    elif milestone_type == "deep_talk":
        topic = context.get("topic_summary", "各种话题")
        prompt += (
            f"你们进行了一次超过 20 轮的深度对话，聊了 {topic}。"
            "请用 2-3 句话回忆这次长谈，不超过 100 字，有温度。"
        )
    elif milestone_type == "memory_breakthrough":
        memory_snippet = context.get("memory_snippet", "一段往事")
        prompt += (
            f"这是你第一次真正回忆起了用户的过去：{memory_snippet}。"
            "请用 1-2 句话描述「终于记住了」的感觉，不超过 80 字。"
        )
    elif milestone_type == "emotion_peak":
        emotion = context.get("dominant_emotion", "强烈的情绪")
        prompt += (
            f"你注意到用户连续表现出了{emotion}。"
            "请用 1-2 句话表达你的观察和关心，不超过 80 字。"
        )
    elif milestone_type == "knowledge_milestone":
        topic = context.get("topic", "某个话题")
        count = context.get("count", 10)
        prompt += (
            f"你发现用户已经是第 {count} 次聊到「{topic}」了。"
            "请用 2-3 句话总结用户对这个话题的热情，不超过 100 字。"
        )
    elif milestone_type == "loyalty_milestone":
        days = context.get("days", 7)
        prompt += (
            f"用户已经连续 {days} 天和你互动了。"
            "请用 1-2 句话表达这段陪伴的感受，不超过 80 字，温暖不煽情。"
        )
    elif milestone_type == "level_unlock":
        new_level = context.get("new_level", 5)
        prompt += (
            f"你和用户的关系升到了 Lv.{new_level}。"
            "请用 1-2 句话描述你们关系的变化，不超过 80 字，语气里有成长感。"
        )

    prompt += "\n直接输出描述文字，不要加引号或前缀。"
    return prompt


async def generate_milestone_description(
    chat_client: LLMClient | None,
    persona_name: str,
    persona_prompt_snippet: str,
    milestone_type: str,
    context: dict | None = None,
) -> str:
    """用 LLM 生成里程碑的故事化描述。chat_client 为 None 时返回模板描述。"""
    if chat_client is None:
        meta = MILESTONE_TYPES.get(milestone_type, {})
        return meta.get("description_template", "里程碑")

    prompt = _build_milestone_prompt(
        persona_name,
        persona_prompt_snippet,
        milestone_type,
        context or {},
    )
    try:
        answer = await chat_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=200,
        )
        return answer.strip().strip('"').strip("'")
    except Exception as e:
        logger.warning("里程碑描述生成失败: type=%s err=%s", milestone_type, e)
        meta = MILESTONE_TYPES.get(milestone_type, {})
        return meta.get("description_template", "里程碑")


def build_milestone(
    persona_id: uuid.UUID,
    user_id: uuid.UUID,
    milestone_type: str,
    title: str,
    description: str,
    level_at_trigger: int | None = None,
    triggered_by_message_id: uuid.UUID | None = None,
    memory_entity_ids: list[str] | None = None,
) -> PersonaMilestone:
    """构建一个里程碑 ORM 对象（不写入 DB，由调用方负责持久化）。"""
    return PersonaMilestone(
        persona_id=persona_id,
        user_id=user_id,
        milestone_type=milestone_type,
        level_at_trigger=level_at_trigger,
        title=title,
        description=description,
        triggered_by_message_id=triggered_by_message_id,
        memory_entities=memory_entity_ids or [],
        occurred_at=datetime.now(timezone.utc),
    )


def check_first_meeting(interaction_count_before: int, interaction_count_after: int) -> bool:
    """初次相遇：interaction_count 从 0 → 1。"""
    return interaction_count_before == 0 and interaction_count_after >= 1


def check_deep_talk(conversation_turn_count: int) -> bool:
    """深度长谈：单次会话超过 20 轮。"""
    return conversation_turn_count >= 20


def check_memory_breakthrough(used_old_memory: bool, milestone_type_exists: bool) -> bool:
    """记忆突破：引用了旧记忆且该类型里程碑尚未触发过。"""
    return used_old_memory and not milestone_type_exists


def check_emotion_peak(consecutive_high_emotion_count: int) -> bool:
    """情绪峰值：连续 3+ 条消息情绪 intensity > 0.7。"""
    return consecutive_high_emotion_count >= 3


def check_knowledge_milestone(topic_count: int) -> bool:
    """知识里程碑：同一话题被讨论 ≥10 次。"""
    return topic_count >= 10


def check_loyalty_milestone(consecutive_days: int) -> bool:
    """连续互动：7/30/100/365 天。"""
    return consecutive_days in (7, 30, 100, 365)


def check_level_unlock(old_level: int, new_level: int) -> bool:
    """等级解锁：每升 5 级。"""
    milestone_levels = {5, 10, 15, 20, 25, 30, 40, 50}
    for ml in milestone_levels:
        if old_level < ml <= new_level:
            return True
    return False
