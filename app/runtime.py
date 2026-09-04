# Shared state for the running process. Everything that used to be a global in
# main.py lives here, because the routers and the worker are separate modules
# now and they all need the same redis connection and the same graph.
#
# These are read through get_redis()/get_graph() rather than imported directly.
# `from app.runtime import redis_client` would copy the value at import time,
# which is None, and would never see what lifespan set later.

import asyncio
import logging
from fastapi import HTTPException, Request
import redis.asyncio as aioredis

from app.config import Config

logger = logging.getLogger(__name__)

config = Config()

_redis_client: aioredis.Redis | None = None
_graph = None


def set_runtime(redis_client: aioredis.Redis, graph) -> None:
    # called once from lifespan, after both are actually built
    global _redis_client, _graph
    _redis_client = redis_client
    _graph = graph


def clear_runtime() -> None:
    global _redis_client, _graph
    _redis_client = None
    _graph = None


def get_redis() -> aioredis.Redis:
    # same idea as get_pool() in pool.py: fail with a clear message instead of
    # an AttributeError on None somewhere deep in a handler
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized")
    return _redis_client


def get_graph():
    if _graph is None:
        raise RuntimeError("Agent graph not initialized")
    return _graph


# asyncio only keeps a weak reference to running tasks, so a fire-and-forget
# task can be garbage collected halfway through. holding them here until they
# finish prevents that, and the callback makes sure a crash gets logged instead
# of disappearing.
_background_tasks: set[asyncio.Task] = set()


def spawn(coro, name: str) -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    def _report(t: asyncio.Task) -> None:
        if not t.cancelled() and t.exception():
            logger.error(f"Background task {name} failed: {t.exception()}")

    task.add_done_callback(_report)
    return task


def client_ip(request: Request) -> str:
    # behind the ALB request.client.host is the load balancer, so every user
    # would share one bucket. the left-most X-Forwarded-For entry is the real
    # client. only trust this because nothing reaches the app except through
    # the ALB - exposed directly, a client could forge the header.
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def rate_limit(request: Request) -> None:
    # simple fixed window per IP: count requests in redis, and set the expiry
    # only on the first one so the window starts from that first request
    key = f"ratelimit:{client_ip(request)}"
    async with get_redis().pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, config.rate_limit_window, nx=True)  # nx = don't extend an existing window
        count, _ = await pipe.execute()
    if count > config.rate_limit_requests:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit reached ({config.rate_limit_requests} requests per "
                   f"{config.rate_limit_window}s). Try again shortly.",
        )
