# Job queue built on Redis Streams. Producers push jobs onto the stream,
# workers pull them via a consumer group so each job goes to exactly one
# worker, and results are stashed separately as plain TTL'd keys.

import json
import uuid
import redis.asyncio as aioredis
from app.config import Config


async def push_job(redis: aioredis.Redis, config: Config, topic: str, session_id: str, output_format: str) -> str:
    # generate id here so caller can poll for the result right away
    job_id = str(uuid.uuid4())
    await redis.xadd(config.stream_key, {
        "job_id": job_id,
        "topic": topic,
        "session_id": session_id,
        "output_format": output_format,
    })
    return job_id


async def get_result(redis: aioredis.Redis, config: Config, job_id: str) -> dict | None:
    # None means not finished yet (or job_id never existed)
    data = await redis.get(f"result:{job_id}")
    return json.loads(data) if data else None


async def set_result(redis: aioredis.Redis, config: Config, job_id: str, result: dict) -> None:
    # TTL so results don't pile up forever if nobody collects them
    await redis.setex(f"result:{job_id}", config.result_ttl, json.dumps(result))


async def ensure_group(redis: aioredis.Redis, config: Config) -> None:
    # id="0" replays any jobs already on the stream, mkstream=True creates
    # the stream if it doesn't exist yet. Errors here just mean the group
    # already exists, safe to ignore.
    try:
        await redis.xgroup_create(config.stream_key, config.consumer_group, id="0", mkstream=True)
    except Exception:
        pass


async def consume_jobs(redis: aioredis.Redis, config: Config) -> list[dict]:
    # ">" means only new/undelivered messages, block=5000 waits up to 5s
    # for one instead of returning empty right away
    messages = await redis.xreadgroup(
        config.consumer_group,
        config.consumer_name,
        {config.stream_key: ">"},
        count=1,
        block=5000,
    )
    if not messages:
        return []
    jobs = []
    for _, entries in messages:
        for msg_id, data in entries:
            jobs.append({"msg_id": msg_id, "data": data})
    return jobs


async def ack_job(redis: aioredis.Redis, config: Config, msg_id: str) -> None:
    # tell the group this job is done so it won't show up in pending list
    await redis.xack(config.stream_key, config.consumer_group, msg_id)
