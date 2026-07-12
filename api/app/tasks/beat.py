"""定时任务（Celery beat）：每日回顾批量生成。

每天定时为所有用户生成当日回顾简报，写入 daily_reviews。
与文档/记忆任务一致：任务级独立引擎 + 独立事件循环。
"""
import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.models  # noqa: F401  确保 ORM 模型注册
from app.celery_app import celery_app
from app.core.logging import get_logger
from app.db.postgres import create_task_engine
from app.models.user_model import User
from app.services.daily_review_service import DailyReviewService

logger = get_logger(__name__)


async def _run() -> int:
    engine = create_task_engine()
    session_maker = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    count = 0
    try:
        async with session_maker() as session:
            result = await session.execute(select(User.id))
            user_ids = [row[0] for row in result.all()]
            service = DailyReviewService(session)
            for uid in user_ids:
                try:
                    # 批量生成走同步全量方法（celery 任务本就可以等），
                    # 不用 get_or_generate 的「派后台 asyncio 任务」路径——celery 任务
                    # 的事件循环结束后后台任务会被丢弃。
                    await service.generate_now(uid)
                    count += 1
                except Exception as e:
                    logger.warning("用户 %s 每日回顾生成失败: %s", uid, e)
    finally:
        await engine.dispose()
    logger.info("每日回顾批量生成完成: %d 个用户", count)
    return count


@celery_app.task(name="app.tasks.beat.generate_daily_reviews")
def generate_daily_reviews_task() -> int:
    """每日回顾批量生成的 Celery 任务入口。"""
    return asyncio.run(_run())


async def _run_clustering() -> int:
    """为所有用户跑一次全量社区聚类（定时兜底纠偏）。"""
    from app.core.llm.resolver import get_optional_client_for_type
    from app.core.memory.clustering.label_propagation import LabelPropagationEngine


    engine_db = create_task_engine()
    session_maker = async_sessionmaker(
        engine_db, expire_on_commit=False, class_=AsyncSession
    )
    count = 0
    try:
        async with session_maker() as session:
            result = await session.execute(select(User.id))
            user_ids = [row[0] for row in result.all()]
            for uid in user_ids:
                try:
                    chat_client = await get_optional_client_for_type(
                        session, uid, "chat"
                    )
                    engine = LabelPropagationEngine(chat_client=chat_client)
                    await engine.full_clustering(str(uid))
                    count += 1
                except Exception as e:
                    logger.warning("用户 %s 全量聚类失败: %s", uid, e)
    finally:
        await engine_db.dispose()
    logger.info("全量社区聚类完成: %d 个用户", count)
    return count


@celery_app.task(name="app.tasks.beat.cluster_communities")
def cluster_communities_task() -> int:
    """全量社区聚类的 Celery 任务入口（定时兜底）。"""
    return asyncio.run(_run_clustering())


async def _run_consolidation() -> int:
    """为所有用户跑一次记忆巩固（短期→长期 + 画像增强）。"""
    from app.core.llm.resolver import get_optional_client_for_type
    from app.core.memory.consolidation.consolidator import ConsolidationEngine


    engine_db = create_task_engine()
    session_maker = async_sessionmaker(
        engine_db, expire_on_commit=False, class_=AsyncSession
    )
    count = 0
    try:
        async with session_maker() as session:
            result = await session.execute(select(User.id))
            user_ids = [row[0] for row in result.all()]
            for uid in user_ids:
                try:
                    chat_client = await get_optional_client_for_type(
                        session, uid, "chat"
                    )
                    engine = ConsolidationEngine(chat_client=chat_client)
                    await engine.run(str(uid))
                    count += 1
                except Exception as e:
                    logger.warning("用户 %s 记忆巩固失败: %s", uid, e)
    finally:
        await engine_db.dispose()
    logger.info("记忆巩固批量完成: %d 个用户", count)
    return count


@celery_app.task(name="app.tasks.beat.consolidate_memory")
def consolidate_memory_task() -> int:
    """记忆巩固的 Celery 任务入口（定时）。"""
    return asyncio.run(_run_consolidation())


async def _run_reflection() -> int:
    """为所有用户跑一次反思（归纳高层洞察 Insight）。"""
    from app.core.llm.resolver import get_optional_client_for_type
    from app.core.memory.reflection.reflector import ReflectionEngine


    engine_db = create_task_engine()
    session_maker = async_sessionmaker(
        engine_db, expire_on_commit=False, class_=AsyncSession
    )
    count = 0
    try:
        async with session_maker() as session:
            result = await session.execute(select(User.id))
            user_ids = [row[0] for row in result.all()]
            for uid in user_ids:
                try:
                    chat_client = await get_optional_client_for_type(
                        session, uid, "chat"
                    )
                    embed_client = await get_optional_client_for_type(
                        session, uid, "embedding"
                    )
                    engine = ReflectionEngine(
                        chat_client=chat_client, embed_client=embed_client
                    )
                    await engine.run(str(uid))
                    count += 1
                except Exception as e:
                    logger.warning("用户 %s 反思失败: %s", uid, e)
    finally:
        await engine_db.dispose()
    logger.info("反思批量完成: %d 个用户", count)
    return count


@celery_app.task(name="app.tasks.beat.reflect_memory")
def reflect_memory_task() -> int:
    """反思的 Celery 任务入口（定时）。"""
    return asyncio.run(_run_reflection())


async def _run_reflection_for_user(user_id: str) -> dict:
    """对单个用户跑一次反思（增量触发用）。"""
    from app.core.llm.resolver import get_optional_client_for_type
    from app.core.memory.reflection.reflector import ReflectionEngine


    engine_db = create_task_engine()
    session_maker = async_sessionmaker(
        engine_db, expire_on_commit=False, class_=AsyncSession
    )
    try:
        async with session_maker() as session:
            uid = uuid.UUID(user_id)
            chat_client = await get_optional_client_for_type(session, uid, "chat")
            embed_client = await get_optional_client_for_type(
                session, uid, "embedding"
            )
            engine = ReflectionEngine(
                chat_client=chat_client, embed_client=embed_client
            )
            return await engine.run(user_id)
    finally:
        await engine_db.dispose()


@celery_app.task(name="app.tasks.beat.reflect_user")
def reflect_user_task(user_id: str) -> dict:
    """单用户反思的 Celery 任务入口（萃取攒够 N 条后增量触发）。"""
    return asyncio.run(_run_reflection_for_user(user_id))


# ── Statement 语义去重 ──

async def _run_statement_dedup() -> int:
    """为所有用户扫描并合并语义重复的 Statement。"""
    from app.repositories.neo4j.memory_graph_repository import MemoryGraphRepository

    engine_db = create_task_engine()
    session_maker = async_sessionmaker(
        engine_db, expire_on_commit=False, class_=AsyncSession
    )
    merged_total = 0
    repo = MemoryGraphRepository()
    try:
        async with session_maker() as session:
            result = await session.execute(select(User.id))
            user_ids = [row[0] for row in result.all()]
            for uid in user_ids:
                user_str = str(uid)
                try:
                    # 扫描高度相似的 Statement 对
                    dups = await repo.find_duplicate_statements(
                        user_str, min_score=0.92, top_k=5, limit=50
                    )
                    for d in dups:
                        source_id = d.get("source_id", "")
                        target_id = d.get("target_id", "")
                        if not source_id or not target_id:
                            continue
                        # 保留较早的作为 target，合并较新的
                        source_created = d.get("source_created", "")
                        target_created = d.get("target_created", "")
                        if source_created < target_created:
                            # source 更早 → 保留 source，合并 target
                            source_id, target_id = target_id, source_id
                        try:
                            await repo.merge_duplicate_statement(
                                user_str, source_id, target_id
                            )
                            merged_total += 1
                        except Exception as e:
                            logger.warning(
                                "Statement 合并失败: source=%s target=%s err=%s",
                                source_id, target_id, e,
                            )
                except Exception as e:
                    logger.warning("用户 %s Statement 去重扫描失败: %s", uid, e)
    finally:
        await engine_db.dispose()
    logger.info("Statement 语义去重完成: 合并 %d 对", merged_total)
    return merged_total


@celery_app.task(name="app.tasks.beat.dedup_statements")
def dedup_statements_task() -> int:
    """Statement 语义去重的 Celery 任务入口（定时）。"""
    return asyncio.run(_run_statement_dedup())


# ── 免疫记录定期清理（30 天 TTL）──

async def _run_correction_cleanup(retention_days: int = 30) -> int:
    """删除超过 retention_days 天的 CorrectionRecord。"""
    from app.repositories.neo4j.memory_graph_repository import MemoryGraphRepository

    repo = MemoryGraphRepository()
    deleted = await repo.cleanup_correction_records(retention_days)
    logger.info("CorrectionRecord 清理完成: retention=%d天 deleted=%d", retention_days, deleted)
    return deleted


@celery_app.task(name="app.tasks.beat.cleanup_correction_records")
def cleanup_correction_records_task() -> int:
    """CorrectionRecord TTL 清理的 Celery 任务入口（定时）。"""
    return asyncio.run(_run_correction_cleanup())
