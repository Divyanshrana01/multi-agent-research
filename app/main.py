# FastAPI entrypoint — wires everything together. A request doesn't wait for the
# agents to finish: /research drops a job on the redis stream and returns a job_id,
# a background worker in this same process picks it up, and the client polls
# /result/{job_id} until it's done.

import asyncio
import base64
import uuid
import logging
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, Request, Depends, APIRouter, Query
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import redis.asyncio as aioredis

# logging is set up before the app imports below on purpose, so every module's
# logger picks up this json format. that's why these imports aren't all at the top.
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)

from app.config import Config
from app.pool import init_pool, close_pool, get_pool
from app.auth import require_api_key
from app.cache import cache_get, cache_set
from app.guardrails import validate_input, validate_output
from app.memory import (
    session_add, session_get, ltm_search, ltm_search_related, ltm_store,
    ltm_diff, db_migrate, list_reports, get_report,
)
from app.queue import push_job, get_result, set_result, ensure_group, consume_jobs, ack_job
from app.agents import build_graph, ResearchState
from app.output import generate_pdf_async, generate_json_report, get_report_diff
from app.eval import evaluate_report, run_batch_evaluation, fetch_recent_topics

config = Config()
# these two are filled in on startup (see lifespan) and used everywhere below
redis_client: aioredis.Redis | None = None
graph = None

# asyncio only keeps a weak reference to running tasks, so a fire-and-forget
# task can be garbage collected halfway through. holding them here until they
# finish prevents that, and the callback makes sure a crash gets logged instead
# of disappearing.
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro, name: str) -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    def _report(t: asyncio.Task) -> None:
        if not t.cancelled() and t.exception():
            logger.error(f"Background task {name} failed: {t.exception()}")

    task.add_done_callback(_report)
    return task


def _client_ip(request: Request) -> str:
    # behind the ALB request.client.host is the load balancer, so every user
    # would share one bucket. the left-most X-Forwarded-For entry is the real
    # client. only trust this because nothing reaches the app except through
    # the ALB - exposed directly, a client could forge the header.
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _rate_limit(request: Request) -> None:
    # simple fixed window per IP: count requests in redis, and set the expiry
    # only on the first one so the window starts from that first request
    key = f"ratelimit:{_client_ip(request)}"
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, config.rate_limit_window, nx=True)  # nx = don't extend an existing window
        count, _ = await pipe.execute()
    if count > config.rate_limit_requests:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit reached ({config.rate_limit_requests} requests per "
                   f"{config.rate_limit_window}s). Try again shortly.",
        )


async def _worker_loop():
    # background loop that pulls jobs off the stream forever
    await ensure_group(redis_client, config)
    while True:
        try:
            jobs = await consume_jobs(redis_client, config)
            for job in jobs:
                # run as a task so a slow job doesn't stop us reading the next one
                _spawn(_process_job(job["data"], job["msg_id"]), f"job:{job['msg_id']}")
        except asyncio.CancelledError:
            # shutdown — let the loop actually stop instead of retrying forever
            raise
        except Exception:
            # never let the loop die, but say what went wrong. a silent retry
            # here is what turns "no jobs are running" into an hour of guessing.
            logger.exception("Worker loop error, retrying in 1s")
            await asyncio.sleep(1)


async def _process_job(data: dict, msg_id: str):
    """
    Does the actual work for one job. Tries the cheapest option first:
    semantic cache -> long-term memory -> full agent pipeline.
    """
    job_id = data["job_id"]
    topic = data["topic"]
    session_id = data["session_id"]
    output_format = data.get("output_format", "text")
    # per-job logger so every line for this job is easy to grep by its short id
    log = logging.getLogger(f"job.{job_id[:8]}")
    try:
        log.info(f"Starting job for topic: {topic}")

        # Fetch session history before any branch — agent always receives it
        session_history = await session_get(redis_client, session_id)

        # which of the three paths below answered this job. reported back to
        # the client so the UI can show whether any agents actually ran.
        source = "pipeline"

        # 1. someone asked something similar recently — reuse it, no LLM calls at all
        cached = await cache_get(redis_client, config, topic)
        if cached:
            log.info("Cache hit")
            source = "cache"
            report_text = cached
            await ltm_store(config, topic, report_text, str(uuid.uuid4()), source)
        else:
            # 2. not in cache, but we may have written a report on this before
            ltm_hit = await ltm_search(config, topic)
            if ltm_hit:
                log.info("LTM hit")
                source = "ltm"
                report_text = ltm_hit["report"]
                await ltm_store(config, topic, report_text, str(uuid.uuid4()), source)
            else:
                # 3. genuinely new topic — pay for the full agent run
                log.info("Running multi-agent pipeline")
                # Find a related (not identical) previous report for the writer to reference
                ltm_context = await ltm_search_related(config, topic) or ""
                if ltm_context:
                    log.info("Found related LTM context for writer agent")
                state = ResearchState(
                    topic=topic,
                    session_id=session_id,
                    session_history=session_history,  # agent is now context-aware
                    ltm_context=ltm_context,           # writer builds on prior research
                    search_results=[],
                    summaries=[],
                    report="",
                    verified=False,
                    error="",
                    iterations=0,
                )
                final_state = await graph.ainvoke(state)
                report_text = final_state["report"]

                # only freshly generated text needs the output guardrail —
                # anything from cache/LTM was already checked when first written
                ok, reason = await validate_output(config, report_text)
                if not ok:
                    # no explicit ack here — the finally block below always acks,
                    # and acking twice was just a no-op round trip to redis
                    log.warning(f"Output guardrail blocked the report: {reason}")
                    await set_result(redis_client, config, job_id, {"status": "blocked", "error": reason})
                    return
                # save it both ways: cache for speed, LTM so it's kept long-term
                await cache_set(redis_client, config, topic, report_text)
                await ltm_store(config, topic, report_text, str(uuid.uuid4()), source)

        await session_add(redis_client, config, session_id, "assistant", report_text[:config.session_content_truncate])
        diff = await ltm_diff(config, topic)
        result: dict = {
            "status": "done", "topic": topic, "report": report_text,
            "diff": diff, "source": source,
        }

        # Per-query evaluation runs automatically on every job.
        # spawned so the user isn't waiting on 4 extra LLM judge calls.
        _spawn(evaluate_report(config, job_id, topic, report_text), f"eval:{job_id[:8]}")

        # results are stored as json, so a pdf has to be base64'd to fit in there
        if output_format == "pdf":
            pdf_bytes = await generate_pdf_async(topic, report_text)
            result["pdf_base64"] = base64.b64encode(pdf_bytes).decode()
        elif output_format == "json":
            result["structured"] = generate_json_report(
                topic, report_text, job_id, datetime.now(timezone.utc)
            )

        await set_result(redis_client, config, job_id, result)
        log.info("Job completed successfully")
    except Exception as e:
        # store the error as the result so the poller sees a failure instead of
        # waiting forever for a job that already died
        log.error(f"Job failed: {traceback.format_exc()}")
        await set_result(redis_client, config, job_id, {"status": "error", "error": str(e)})
    finally:
        # ack no matter what, otherwise the job sits in the pending list forever
        await ack_job(redis_client, config, msg_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # everything before the yield runs on startup, everything after on shutdown.
    # order matters: connections and tables first, then the graph, then the worker.
    global redis_client, graph
    redis_client = await aioredis.from_url(config.redis_url, decode_responses=True)
    await init_pool(config)
    await db_migrate(config)  # creates the reports table/indexes if they don't exist
    graph = build_graph(config)
    app.state.config = config
    worker = _spawn(_worker_loop(), "worker-loop")  # runs in the same process as the API
    logger.info("Startup complete")

    yield

    # stop the worker before tearing down its connections, otherwise it wakes
    # up mid-shutdown and logs errors about a closed redis client
    worker.cancel()
    try:
        await worker
    except asyncio.CancelledError:
        pass
    await redis_client.aclose()
    await close_pool()
    logger.info("Shutdown complete")


app = FastAPI(title="Research Agent API", lifespan=lifespan)

# every data endpoint lives under /api. that keeps the URL space clear for the
# frontend's own routes (/reports, /settings), which the catch-all at the bottom
# of this file hands to react-router.
api = APIRouter(prefix="/api")

# in dev the frontend runs on vite's own port (5173) and calls this server, so
# it needs CORS. in production both come from this origin and it's unused.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class ResearchRequest(BaseModel):
    # pydantic rejects junk before it reaches redis or an LLM: an empty topic,
    # a novel pasted into the box, or a made-up output format
    topic: str = Field(min_length=3, max_length=500)
    session_id: str = Field(default="", max_length=100)
    output_format: Literal["text", "pdf", "json"] = "text"


# the built frontend. vite writes it here; the Dockerfile copies the same path.
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@app.get("/health")
async def health():
    # no auth on this one — the load balancer needs to hit it to know we're alive
    try:
        await redis_client.ping()
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


@api.post("/research", dependencies=[Depends(require_api_key), Depends(_rate_limit)])
async def start_research(req: ResearchRequest):
    # guardrail the question before it costs us anything
    ok, reason = await validate_input(config, req.topic)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)
    # no session_id sent means this is a new conversation
    session_id = req.session_id or str(uuid.uuid4())
    await session_add(redis_client, config, session_id, "user", req.topic)
    # returns straight away — the worker does the slow part
    job_id = await push_job(redis_client, config, req.topic, session_id, req.output_format)
    return {"job_id": job_id, "session_id": session_id}


@api.get("/result/{job_id}", dependencies=[Depends(require_api_key)])
async def get_job_result(job_id: str):
    # client polls this. no result key yet = still working (or bad job_id).
    result = await get_result(redis_client, config, job_id)
    if result is None:
        return {"status": "pending"}
    return result


@api.get("/session/{session_id}", dependencies=[Depends(require_api_key)])
async def get_session(session_id: str):
    messages = await session_get(redis_client, session_id)
    return {"session_id": session_id, "messages": messages}


@api.get("/diff/{topic}", dependencies=[Depends(require_api_key)])
async def report_diff(topic: str):
    diff = await get_report_diff(config, topic)
    return {"topic": topic, "diff": diff or "No previous report found."}


@api.get("/result/{job_id}/pdf", dependencies=[Depends(require_api_key)])
async def download_pdf(job_id: str):
    # lets you grab a pdf even if the job wasn't started with output_format=pdf
    result = await get_result(redis_client, config, job_id)
    if not result or result.get("status") != "done":
        raise HTTPException(status_code=404, detail="Report not ready")
    # rendering happens in a thread so a long report doesn't stall the server
    pdf_bytes = await generate_pdf_async(result.get("topic", "Report"), result["report"])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={job_id}.pdf"},
    )


@api.get("/stats", dependencies=[Depends(require_api_key)])
async def stats():
    # numbers for the demo dashboard — how much is cached, how many sessions, etc.
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


# re-scores a job on demand. evaluation already runs automatically on every job,
# this is for when I want to look at the scores for one specific report.
@api.get("/evaluate/{job_id}", dependencies=[Depends(require_api_key)])
async def evaluate_job(job_id: str):
    result = await get_result(redis_client, config, job_id)
    if not result or result.get("status") != "done":
        raise HTTPException(status_code=404, detail="Job not done yet")
    scores = await evaluate_report(config, job_id, result["topic"], result["report"])
    return {"job_id": job_id, "topic": result["topic"], "scores": scores}


class BatchEvalRequest(BaseModel):
    # capped because every topic here is a full pipeline run plus 4 judge calls
    topics: list[str] = Field(default_factory=list, max_length=20)


# rate limited as well as key-protected: this is by far the most expensive
# endpoint, and without a limit one script could run up a large model bill
@api.post("/run-evaluation", dependencies=[Depends(require_api_key), Depends(_rate_limit)])
async def trigger_batch_evaluation(req: BatchEvalRequest):
    # no topics given = use whatever people actually asked recently
    topics = req.topics if req.topics else await fetch_recent_topics()
    if not topics:
        raise HTTPException(status_code=400, detail="No topics found. Submit at least one research job first.")
    # re-runs the whole pipeline per topic, so it goes in the background and the
    # caller just gets an acknowledgement
    _spawn(run_batch_evaluation(config, graph, topics), "batch-eval")
    return {"message": "Batch evaluation started in background", "topics": len(topics)}


@api.get("/reports", dependencies=[Depends(require_api_key)])
async def browse_reports(
    limit: int = Query(default=24, ge=1, le=100),
    # cursor is the created_at of the last row the client already has
    cursor: datetime | None = None,
):
    """Newest report per topic, for the library view."""
    rows = await list_reports(limit=limit, before=cursor)
    return {
        "reports": [
            {
                "id": r["id"],
                "topic": r["topic"],
                "preview": r["preview"],
                "word_count": r["word_count"],
                "source": r["source"] or "pipeline",  # rows written before the column existed
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
        # only send a cursor when a full page came back, so the client knows
        # to stop instead of asking for one more empty page
        "next_cursor": rows[-1]["created_at"].isoformat() if len(rows) == limit else None,
    }


@api.get("/reports/{report_id}", dependencies=[Depends(require_api_key)])
async def read_report(report_id: str):
    report = await get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="No report with that id.")
    # the diff is looked up live rather than stored, so it always compares
    # against whatever the latest report on this topic is now
    diff = await ltm_diff(config, report["topic"])
    return {
        "id": report["id"],
        "topic": report["topic"],
        "report": report["report"],
        "word_count": report["word_count"],
        "source": report["source"] or "pipeline",
        "created_at": report["created_at"].isoformat(),
        "diff": diff,
    }


app.include_router(api)


# Mounted after every route above, so nothing here can shadow /api or /health.
# Only mounted when a build exists — without it the API still runs fine, which
# is what you want when working on the backend alone.
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        # any non-API path returns the app shell and lets react-router decide
        # what to render, so refreshing on /reports/abc works like a real URL
        candidate = DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)  # favicon, robots.txt, and friends
        return FileResponse(DIST / "index.html")
else:
    @app.get("/")
    async def no_frontend():
        return {
            "detail": "No frontend build found. Run `npm install && npm run build` in frontend/, "
                      "or use the Vite dev server on :5173.",
        }
