"""角色日记定时生成任务：每天 23:00 为有互动的角色生成日记。"""
import asyncio
from datetime import date, datetime, time

from sqlalchemy import select, distinct

from app.celery_app import celery_app
from app.core.llm.chat_model import build_default_chat_model
from app.core.llm.client import LLMClient
from app.core.logging import get_logger
from app.core.persona.diary_writer import collect_daily_context, generate_diary
from app.db.postgres import create_task_engine
from app.models.agent_persona_model import AgentPersona
from app.models.conversation_model import Conversation, Message
from app.models.persona_diary_model import PersonaDiary
from app.models.persona_growth_model import PersonaGrowth
from app.repositories.persona_diary_repository import PersonaDiaryRepository

logger = get_logger(__name__)

BATCH_SIZE = 50  # 每批处理的用户数


@celery_app.task(
    name="app.tasks.persona_diary.generate_persona_diaries",
    queue="beat",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=300,
)
def generate_persona_diaries() -> dict:
    """每天 23:00 触发：为所有今天有互动的 (用户, 角色) 对生成日记。"""
    return asyncio.run(_run())


async def _run() -> dict:
    engine = create_task_engine()
    total_diaries = 0
    total_errors = 0

    try:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        async with sm() as session:
            today = date.today()
            day_start = datetime.combine(today, time.min)
            day_end = datetime.combine(today, time.max)

            # 找今天有互动的 (user_id, persona_id) 去重对
            result = await session.execute(
                select(distinct(Conversation.user_id), Conversation.persona_id)
                .join(Message, Message.conversation_id == Conversation.id)
                .where(
                    Message.created_at >= day_start,
                    Message.created_at <= day_end,
                    Conversation.persona_id.isnot(None),
                )
            )
            pairs = [(row[0], row[1]) for row in result.all()]
            logger.info("日记生成: 今天有 %d 个活跃 (用户, 角色) 对", len(pairs))

            for user_id, persona_id in pairs:
                try:
                    # 检查是否已有今日日记
                    diary_repo = PersonaDiaryRepository(session)
                    exists = await diary_repo.exists_for_date(persona_id, user_id, today)
                    if exists:
                        continue

                    # 获取角色信息
                    persona_result = await session.execute(
                        select(AgentPersona).where(AgentPersona.id == persona_id)
                    )
                    persona = persona_result.scalar_one_or_none()
                    if persona is None:
                        continue

                    # 获取成长数据
                    growth_result = await session.execute(
                        select(PersonaGrowth).where(
                            PersonaGrowth.persona_id == persona_id,
                            PersonaGrowth.user_id == user_id,
                        )
                    )
                    growth = growth_result.scalar_one_or_none()
                    level = growth.level if growth else 1
                    intimacy = growth.intimacy if growth else 0.0

                    # 收集上下文
                    ctx = await collect_daily_context(session, persona_id, user_id, today)
                    if not ctx["had_interactions"]:
                        continue

                    # 构建 LLM client
                    chat_client = None
                    try:
                        _, model_config = await build_default_chat_model(
                            session, user_id, temperature=0.85, streaming=False
                        )
                        from app.core.security import decrypt_secret
                        chat_client = LLMClient(
                            model_config.base_url,
                            decrypt_secret(model_config.api_key_encrypted),
                            model_config.model_name,
                        )
                    except Exception as e:
                        logger.warning("日记 LLM 初始化失败: user=%s err=%s", user_id, e)

                    # 生成日记
                    diary_data = await generate_diary(
                        chat_client,
                        persona.name,
                        persona.system_prompt[:200],
                        level,
                        intimacy,
                        ctx,
                    )

                    # 存入数据库
                    diary = PersonaDiary(
                        persona_id=persona_id,
                        user_id=user_id,
                        diary_date=today,
                        content=diary_data["content"],
                        title=diary_data.get("title"),
                        mood=diary_data.get("mood", "neutral"),
                        key_topics=diary_data.get("key_topics", []),
                        key_insights=diary_data.get("key_insights", []),
                        word_count=diary_data.get("word_count", 0),
                    )
                    await diary_repo.create(diary)
                    total_diaries += 1

                except Exception as e:
                    logger.error("日记生成失败: user=%s persona=%s err=%s", user_id, persona_id, e)
                    total_errors += 1

            logger.info("日记生成完成: 成功=%d 失败=%d", total_diaries, total_errors)
    finally:
        await engine.dispose()

    return {"total": total_diaries, "errors": total_errors}
