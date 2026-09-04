# The background worker. It runs in the same process as the API: /research
# pushes a job onto the redis stream and returns, and the loop here picks it up
# and does the slow part.

import asyncio
import base64
import logging
import traceback
import uuid
from datetime import datetime, timezone

from app.runtime import config, get_redis, get_graph, spawn
from app.cache import cache_get, cache_set
from app.guardrails import validate_output
from app.memory import session_add, session_get, ltm_search, ltm_search_related, ltm_store, ltm_diff
from app.queue import set_result, ensure_group, consume_jobs, ack_job
from app.agents import ResearchState
from app.output import generate_pdf_async, generate_json_report
from app.eval import evaluate_report

logger = logging.getLogger(__name__)


async def worker_loop():
    # background loop that pulls jobs off the stream forever
    redis_client = get_redis()
    await ensure_group(redis_client, config)
    while True:
        try:
            jobs = await consume_jobs(redis_client, config)
            for job in jobs:
                # run as a task so a slow job doesn't stop us reading the next one
                spawn(process_job(job["data"], job["msg_id"]), f"job:{job['msg_id']}")
        except asyncio.CancelledError:
            # shutdown — let the loop actually stop instead of retrying forever
            raise
        except Exception:
            # never let the loop die, but say what went wrong. a silent retry
            # here is what turns "no jobs are running" into an hour of guessing.
            logger.exception("Worker loop error, retrying in 1s")
            await asyncio.sleep(1)


async def process_job(data: dict, msg_id: str):
    """
    Does the actual work for one job. Tries the cheapest option first:
    semantic cache -> long-term memory -> full agent pipeline.
    """
    redis_client = get_redis()
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
                final_state = await get_graph().ainvoke(state)
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
        spawn(evaluate_report(config, job_id, topic, report_text), f"eval:{job_id[:8]}")

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
