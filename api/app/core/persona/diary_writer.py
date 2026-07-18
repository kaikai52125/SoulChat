"""日记生成引擎：收集每日对话上下文，调用 LLM 生成角色第一人称日记。"""
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.client import LLMClient
from app.core.logging import get_logger
from app.models.conversation_model import Message, ROLE_USER
from app.models.emotion_model import EmotionRecord

logger = get_logger(__name__)

# 日记长度约束
DIARY_MIN_CHARS = 150
DIARY_MAX_CHARS = 400

# 收集的上下文数量
MAX_RECENT_MESSAGES = 20


async def collect_daily_context(
    session: AsyncSession,
    persona_id: uuid.UUID,
    user_id: uuid.UUID,
    target_date: date,
) -> dict:
    """收集一天的对话上下文、情绪数据和记忆实体。"""
    from datetime import time

    day_start = datetime.combine(target_date, time.min)
    day_end = datetime.combine(target_date, time.max)

    # ── 当日该角色发的消息(仅该 persona 与目标用户的对话) ──
    from app.models.conversation_model import Conversation
    msg_result = await session.execute(
        select(Message.content, Message.role)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.user_id == user_id,
            Conversation.persona_id == persona_id,
            Message.sender_persona_id == persona_id,
            Message.created_at >= day_start,
            Message.created_at <= day_end,
        )
        .order_by(Message.created_at.asc())
        .limit(MAX_RECENT_MESSAGES)
    )
    messages = [
        {"role": role, "content": content}
        for content, role in msg_result.all()
    ]

    # ── 当日用户在同一个对话中的发言 ──
    user_msg_result = await session.execute(
        select(Message.content)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.user_id == user_id,
            Conversation.persona_id == persona_id,
            Message.role == ROLE_USER,
            Message.created_at >= day_start,
            Message.created_at <= day_end,
        )
        .order_by(Message.created_at.asc())
        .limit(MAX_RECENT_MESSAGES)
    )
    user_messages = [row[0] for row in user_msg_result.all()]

    # ── 当日情绪记录 ──
    emotion_result = await session.execute(
        select(EmotionRecord.valence, EmotionRecord.intensity, EmotionRecord.emotion_type)
        .where(
            EmotionRecord.user_id == user_id,
            EmotionRecord.created_at >= day_start,
            EmotionRecord.created_at <= day_end,
        )
        .order_by(EmotionRecord.created_at.asc())
    )
    emotions = [
        {"valence": v, "intensity": i, "type": t}
        for v, i, t in emotion_result.all()
    ]

    return {
        "messages": messages,
        "user_messages": user_messages,
        "emotions": emotions,
        "message_count": len(messages),
        "had_interactions": len(messages) > 0,
    }


def _build_diary_prompt(
    persona_name: str,
    persona_prompt_snippet: str,
    growth_level: int,
    intimacy: float,
    context: dict,
) -> str:
    """构建日记生成提示词。"""
    message_count = context.get("message_count", 0)
    user_messages = context.get("user_messages", [])
    emotions = context.get("emotions", [])

    # 情绪摘要
    mood_summary = "平稳"
    if emotions:
        avg_valence = sum(e["valence"] for e in emotions) / len(emotions)
        if avg_valence > 0.5:
            mood_summary = "偏积极、愉悦"
        elif avg_valence > 0.2:
            mood_summary = "比较平和"
        elif avg_valence > -0.2:
            mood_summary = "有些复杂"
        elif avg_valence > -0.5:
            mood_summary = "偏低落"
        else:
            mood_summary = "比较消沉"

    # 话题摘要：取用户消息的前 50 字拼接
    topic_snippets = "、".join(m[:50] for m in user_messages[:5]) if user_messages else "日常闲聊"

    # 根据等级控制洞察深度
    if growth_level < 5:
        depth_instruction = "你对他还不太熟悉，做表面观察即可，不要做深层分析。"
    elif growth_level < 10:
        depth_instruction = "你对他已经有了一些了解，可以做适度的观察和感受。"
    else:
        depth_instruction = "你已经很了解他了，可以给出有深度的观察和温柔的洞察。"

    prompt = (
        f"你是「{persona_name}」，你的性格和说话风格是：\n"
        f"{persona_prompt_snippet}\n\n"
        f"今天（{date.today()}）你和用户聊了 {message_count} 轮，"
        f"话题涉及：{topic_snippets}。\n"
        f"用户今天的情绪基调是：{mood_summary}。\n"
        f"你们的关系等级是 Lv.{growth_level}，亲密度 {intimacy}/100。\n\n"
        f"{depth_instruction}\n\n"
        f"请以第一人称（「我」），用你的语气和风格，写一段 {DIARY_MIN_CHARS}~{DIARY_MAX_CHARS} 字的日记。"
        f"日记应该像朋友写的私密记录：\n"
        f"- 今天和用户聊了什么，你有什么感受\n"
        f"- 你注意到用户今天有什么不同（情绪、话题、语气的变化）\n"
        f"- 有什么你想记住的、或者明天想关心的\n"
        f"- 语气要自然、有温度、不完全像 AI 写的\n"
        f"- 可以有一两句自嘲或幽默（如果你的性格里有这一面的话）\n"
        f"- 不要把日记写成「日报总结」——这是你的内心独白，不是工作汇报\n\n"
        f"重要：如果用户提到了其他AI角色或助手（如\"泰哥\"\"小彗\"等），不要在日记中提及他们——日记只关于你（{persona_name}）和用户的关系。也不要透露用户的真实姓名、地址、电话等隐私。"
        f"\n\n请用以下格式回复："
        f"\n第一行：简短标题（15字以内，不要引号）"
        f"\n空一行"
        f"\n正文内容"
    )
    return prompt


async def generate_diary(
    chat_client: LLMClient | None,
    persona_name: str,
    persona_prompt_snippet: str,
    growth_level: int,
    intimacy: float,
    context: dict,
) -> dict:
    """生成一篇日记。返回 {content, title, mood, key_topics, key_insights, word_count}。

    chat_client 为 None 时返回占位内容。
    """
    if chat_client is None:
        return {
            "content": f"（日记功能需要配置 LLM 模型）\n\n今天和 {persona_name} 聊了 {context.get('message_count', 0)} 轮。",
            "title": "今日无日记",
            "mood": "neutral",
            "key_topics": [],
            "key_insights": [],
            "word_count": 0,
        }

    prompt = _build_diary_prompt(
        persona_name, persona_prompt_snippet, growth_level, intimacy, context
    )

    try:
        content = await chat_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=600,
        )
        content = content.strip()

        # 提取标题：LLM 应该在第一行返回标题，空行后是正文
        title = None
        lines = content.split("\n")
        if len(lines) >= 2 and lines[0].strip() and not lines[1].strip():
            # 第一行有内容，第二行为空 → 第一行是标题
            title = lines[0].strip()[:30]
            content = "\n".join(lines[2:]).strip()
        if not title:
            # 回退：取第一句
            first_sentence = content.split("。")[0].split("！")[0].split("？")[0]
            title = first_sentence[:30] if len(first_sentence) > 30 else first_sentence

        # 简单推断 mood
        mood = "neutral"
        if any(w in content for w in ["开心", "高兴", "温暖", "欣慰", "感动"]):
            mood = "warm"
        elif any(w in content for w in ["担心", "心疼", "焦虑", "难过"]):
            mood = "concerned"
        elif any(w in content for w in ["有趣", "好笑", "逗", "笑"]):
            mood = "playful"
        elif any(w in content for w in ["骄傲", "自豪", "厉害"]):
            mood = "proud"
        elif any(w in content for w in ["思考", "沉思", "复杂", "纠结"]):
            mood = "thoughtful"

        # 关键话题：简单从用户消息中提取
        user_msgs = context.get("user_messages", [])
        topics = list({m[:20] for m in user_msgs[:3]}) if user_msgs else []

        return {
            "content": content,
            "title": title,
            "mood": mood,
            "key_topics": topics,
            "key_insights": [],
            "word_count": len(content),
        }
    except Exception as e:
        logger.warning("日记生成失败: persona=%s err=%s", persona_name, e)
        return {
            "content": f"（日记生成失败: {e}）",
            "title": "生成失败",
            "mood": "neutral",
            "key_topics": [],
            "key_insights": [],
            "word_count": 0,
        }
