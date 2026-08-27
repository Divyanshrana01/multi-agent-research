import logging
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI

from app.config import Config

config = Config.from_env()

logging.basicConfig(level=config.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.from_url(config.redis_url, decode_responses=True)
    app.state.pool = await asyncpg.create_pool(config.database_url, min_size=1, max_size=5)
    logger.info("connected to redis and postgres")
    yield
    await app.state.redis.aclose()
    await app.state.pool.close()


app = FastAPI(title="Research Agent", lifespan=lifespan)


@app.get("/health")
async def health():
    """Reports on each dependency separately.

    A single ok/not-ok would tell me nothing about which one is down.
    """
    try:
        await app.state.redis.ping()
        redis_status = "ok"
    except Exception as exc:
        logger.warning("redis health check failed: %s", exc)
        redis_status = "error"

    try:
        async with app.state.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "ok"
    except Exception as exc:
        logger.warning("postgres health check failed: %s", exc)
        db_status = "error"

    healthy = redis_status == "ok" and db_status == "ok"
    return {
        "status": "ok" if healthy else "degraded",
        "redis": redis_status,
        "db": db_status,
    }
