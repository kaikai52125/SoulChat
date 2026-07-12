"""Neo4j 异步驱动连接（单例用于 API 请求 + create 工厂用于 Celery 多线程任务）。"""
from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import settings

_driver: AsyncDriver | None = None


def _build_driver() -> AsyncDriver:
    return AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        max_connection_pool_size=settings.neo4j_max_pool_size,
        connection_acquisition_timeout=settings.neo4j_connection_timeout,
    )


def get_driver() -> AsyncDriver:
    """API 请求侧：模块级单例，随 uvicorn 生命周期。"""
    global _driver
    if _driver is None:
        _driver = _build_driver()
    return _driver


def create_driver() -> AsyncDriver:
    """Celery 任务侧：每次调用创建新驱动实例，线程安全。"""
    return _build_driver()


async def ping() -> bool:
    try:
        await get_driver().verify_connectivity()
        return True
    except Exception:
        return False


async def close() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
