# Scoring reports with the LLM judges. Per-job evaluation already runs
# automatically in the worker, these endpoints are for looking at one report on
# demand or re-running a whole batch.

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_api_key
from app.runtime import config, get_redis, get_graph, spawn, rate_limit
from app.queue import get_result
from app.eval import evaluate_report, run_batch_evaluation, fetch_recent_topics
from app.api.schemas import BatchEvalRequest

router = APIRouter(tags=["evaluation"], dependencies=[Depends(require_api_key)])


# re-scores a job on demand. evaluation already runs automatically on every job,
# this is for when I want to look at the scores for one specific report.
@router.get("/evaluate/{job_id}")
async def evaluate_job(job_id: str):
    result = await get_result(get_redis(), config, job_id)
    if not result or result.get("status") != "done":
        raise HTTPException(status_code=404, detail="Job not done yet")
    scores = await evaluate_report(config, job_id, result["topic"], result["report"])
    return {"job_id": job_id, "topic": result["topic"], "scores": scores}


# rate limited as well as key-protected: this is by far the most expensive
# endpoint, and without a limit one script could run up a large model bill
@router.post("/run-evaluation", dependencies=[Depends(rate_limit)])
async def trigger_batch_evaluation(req: BatchEvalRequest):
    # no topics given = use whatever people actually asked recently
    topics = req.topics if req.topics else await fetch_recent_topics()
    if not topics:
        raise HTTPException(status_code=400, detail="No topics found. Submit at least one research job first.")
    # re-runs the whole pipeline per topic, so it goes in the background and the
    # caller just gets an acknowledgement
    spawn(run_batch_evaluation(config, get_graph(), topics), "batch-eval")
    return {"message": "Batch evaluation started in background", "topics": len(topics)}
