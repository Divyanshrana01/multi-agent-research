import asyncpg
from fastapi import HTTPException
from app.config import Config

# module-level variable that holds our one shared db pool
# starts as None until init_pool() is called
_pool: asyncpg.Pool | None = None


# creates the db connection pool once, at app startup
# min_size/max_size control how many connections stay open
async def init_pool(config: Config) -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        config.database_url,
        min_size=config.db_pool_min,
        max_size=config.db_pool_max,
    )


# closes all connections in the pool, call this on app shutdown
async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None  # reset so we know it's not initialized anymore


# lets other parts of the app grab the pool to run queries
# errors out if someone tries to use it before init_pool() ran
def get_pool() -> asyncpg.Pool:
    if _pool is None:
        # 503 rather than 500, same reasoning as get_redis() in runtime.py: the
        # server takes requests before startup has opened this pool, and "come
        # back in a second" is true where "something is broken" isn't.
        # written out here instead of shared with runtime.py so importing this
        # module doesn't drag in runtime's config load as a side effect.
        raise HTTPException(
            status_code=503,
            detail="The database is still starting up. Try again in a moment.",
            headers={"Retry-After": "2"},
        )
    return _pool
