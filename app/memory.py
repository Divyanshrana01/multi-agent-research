import difflib
import json
from datetime import datetime
import redis.asyncio as aioredis
from app.config import Config
from app.embeddings import embed
from app.pool import get_pool

# the embedding model lives in app/embeddings.py, shared with the cache, so
# there's only one copy of the weights in memory


# short-term memory (redis)
# this is the "what did we just talk about" memory, only lasts a little while

# saves one message (user's or the agent's) into this session's chat history
async def session_add(redis: aioredis.Redis, config: Config, session_id: str, role: str, content: str) -> None:
    key = f"session:{session_id}"
    # rpush = add to the end of a list in redis
    await redis.rpush(key, json.dumps({"role": role, "content": content}))
    # only keep the last few messages, throw away older ones
    await redis.ltrim(key, -config.session_max_messages, -1)
    # reset the countdown - whole session disappears if unused for a while
    await redis.expire(key, config.session_ttl)


# reads back the whole chat history for a session
async def session_get(redis: aioredis.Redis, session_id: str) -> list[dict]:
    # lrange 0 to -1 = give me every item in the list
    messages = await redis.lrange(f"session:{session_id}", 0, -1)
    # they're stored as json text, so turn each one back into a dict
    return [json.loads(m) for m in messages]


# long-term memory (postgres + pgvector)
# this is the "we researched this topic before" memory, sticks around for days

# creates our table and indexes if they don't exist yet - safe to run every startup
async def db_migrate(config: Config) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        # pgvector is the postgres add-on that lets us store embeddings
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        # one row per report we've written. vector(384) because our model
        # spits out 384 numbers per piece of text
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id         TEXT PRIMARY KEY,
                topic      TEXT NOT NULL,
                report     TEXT NOT NULL,
                embedding  vector(384),
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        # ivfflat index = makes "find me similar embeddings" searches fast
        # instead of postgres comparing against every single row
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS reports_embedding_idx
            ON reports USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = {config.ivfflat_lists})
        """)
        # normal indexes so looking up by topic or by date is also quick
        await conn.execute("CREATE INDEX IF NOT EXISTS reports_topic_idx ON reports (topic)")
        await conn.execute("CREATE INDEX IF NOT EXISTS reports_created_idx ON reports (created_at DESC)")
        # records which path answered the job (pipeline/cache/ltm) so the report
        # library can show it. added separately because CREATE TABLE IF NOT EXISTS
        # won't touch a table that already exists.
        await conn.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS source TEXT")


# saves a finished report so we can find it again later
async def ltm_store(config: Config, topic: str, report: str, report_id: str, source: str = "pipeline") -> None:
    # encoding is slow-ish and blocking, so it runs in a thread (see embeddings.py)
    embedding = await embed(topic)
    pool = get_pool()
    async with pool.acquire() as conn:
        # created_at is left out on purpose so postgres fills it with its own
        # NOW() - one clock for every row, whatever timezone the app runs in
        await conn.execute(
            """
            INSERT INTO reports (id, topic, report, embedding, source)
            VALUES ($1, $2, $3, $4::vector, $5)
            ON CONFLICT (id) DO NOTHING
            """,
            # ON CONFLICT DO NOTHING = if we already saved this id, just skip it
            report_id, topic, report, str(embedding), source,
        )


# looks for a recent report about basically the SAME topic, so we can reuse it
# instead of researching the whole thing again
async def ltm_search(config: Config, topic: str) -> dict | None:
    embedding = await embed(topic)
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, topic, report, created_at,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM reports
            WHERE created_at > NOW() - ($2 || ' days')::INTERVAL
              AND 1 - (embedding <=> $1::vector) > $3
            ORDER BY similarity DESC LIMIT 1
            """,
            # "<=>" is pgvector's distance operator, so 1 - distance = similarity.
            # we only want reports newer than ltm_days and similar enough
            str(embedding), str(config.ltm_days), config.ltm_threshold,
        )
        return dict(row) if row else None


async def ltm_search_related(config: Config, topic: str) -> str | None:
    """
    Finds a related (but not identical) previous report to use as reference context
    for the writer agent. Uses a lower threshold than ltm_search so it finds
    nearby topics rather than exact matches.
    """
    embedding = await embed(topic)
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT report FROM reports
            WHERE created_at > NOW() - ($3 || ' days')::INTERVAL
              AND 1 - (embedding <=> $1::vector) BETWEEN 0.5 AND $2
            ORDER BY created_at DESC LIMIT 1
            """,
            # BETWEEN 0.5 and (threshold - 0.01) = related but deliberately NOT
            # close enough to count as the same topic. the date bound stops the
            # writer being handed a years-old report as "prior research".
            str(embedding), config.ltm_threshold - 0.01, str(config.ltm_related_days),
        )
        return row["report"] if row else None


# lists reports for the library view. one row per topic (the newest), because
# every cache hit re-stores the same report and the list would otherwise be
# mostly duplicates.
async def list_reports(limit: int = 24, before: datetime | None = None) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, topic, created_at, source,
                   left(report, 220) AS preview,
                   coalesce(array_length(regexp_split_to_array(btrim(report), '\\s+'), 1), 0)
                       AS word_count
            FROM (
                SELECT DISTINCT ON (topic) id, topic, report, created_at, source
                FROM reports
                ORDER BY topic, created_at DESC
            ) newest_per_topic
            -- keyset pagination: "everything older than the last row you saw".
            -- OFFSET would get slower the deeper you page.
            WHERE ($1::timestamp IS NULL OR created_at < $1)
            ORDER BY created_at DESC
            LIMIT $2
            """,
            before, limit,
        )
        return [dict(row) for row in rows]


# one full report for the detail view
async def get_report(report_id: str) -> dict | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, topic, report, created_at, source,
                   coalesce(array_length(regexp_split_to_array(btrim(report), '\\s+'), 1), 0)
                       AS word_count
            FROM reports WHERE id = $1
            """,
            report_id,
        )
        return dict(row) if row else None


# compares the two newest reports on a topic and shows what changed between them
async def ltm_diff(config: Config, topic: str) -> str | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        # grab the two most recent reports for this exact topic
        rows = await conn.fetch(
            "SELECT report, created_at FROM reports WHERE topic = $1 ORDER BY created_at DESC LIMIT 2",
            topic,
        )
        # need two reports to compare, if there's only one there's nothing to diff
        if len(rows) < 2:
            return None
        old_lines = rows[1]["report"].splitlines(keepends=True)
        new_lines = rows[0]["report"].splitlines(keepends=True)
        # difflib gives us a git-style diff of the two texts
        diff_lines = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"previous ({rows[1]['created_at'].date()})",
            tofile=f"latest ({rows[0]['created_at'].date()})",
            lineterm="",
        ))
        # cut it off so a huge diff doesn't flood the response
        return "\n".join(diff_lines[:config.ltm_diff_limit * 10]) or "No significant changes detected."
