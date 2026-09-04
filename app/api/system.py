# Health and stats. Two routers here because they have different rules: the
# load balancer hits /health with no api key, /api/stats needs one like
# everything else.

from fastapi import APIRouter, Depends

from app.auth import require_api_key
from app.pool import get_pool
from app.runtime import config, get_redis

# no auth and no /api prefix — the load balancer needs to hit it to know we're alive
health_router = APIRouter(tags=["system"])

router = APIRouter(tags=["system"], dependencies=[Depends(require_api_key)])


@health_router.get("/health")
async def health():
    try:
        await get_redis().ping()
        redis_ok = True
    except Exception:
        redis_ok = False

    # postgres matters just as much as redis: without it every job fails at the
    # memory step, so a redis-only check would report a healthy but broken task
    try:
        async with get_pool().acquire() as conn:
            await conn.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ok" if redis_ok and db_ok else "degraded",
        "redis": "ok" if redis_ok else "error",
        "database": "ok" if db_ok else "error",
    }


@router.get("/stats")
async def stats():
    # numbers for the demo dashboard — how much is cached, how many sessions, etc.
    redis_client = get_redis()
    info = await redis_client.info()
    keys = await redis_client.dbsize()
    # scan_iter instead of KEYS so we don't block redis while counting
    cache_keys = len([k async for k in redis_client.scan_iter("semantic:*")])
    session_keys = len([k async for k in redis_client.scan_iter("session:*")])
    return {
        "redis": {
            "total_keys": keys,
            "cache_entries": cache_keys,
            "active_sessions": session_keys,
            "memory_used_mb": round(info["used_memory"] / 1024 / 1024, 2),
            "connected_clients": info["connected_clients"],
            "uptime_hours": round(info["uptime_in_seconds"] / 3600, 1),
        },
        "tensorzero_url": config.tensorzero_url,
        "guardrail_id": config.bedrock_guardrail_id,
    }
