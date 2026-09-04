# Starting a research job and getting the answer back out.

import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.auth import require_api_key
from app.runtime import config, get_redis, rate_limit
from app.guardrails import validate_input
from app.memory import session_add, session_get
from app.queue import push_job, get_result
from app.output import generate_pdf_async
from app.api.schemas import ResearchRequest

# the api key is checked for every route in this file, so it goes on the router
# instead of being repeated on each one
router = APIRouter(tags=["research"], dependencies=[Depends(require_api_key)])


@router.post("/research", dependencies=[Depends(rate_limit)])
async def start_research(req: ResearchRequest):
    # guardrail the question before it costs us anything
    ok, reason = await validate_input(config, req.topic)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)
    # no session_id sent means this is a new conversation
    session_id = req.session_id or str(uuid.uuid4())
    redis_client = get_redis()
    await session_add(redis_client, config, session_id, "user", req.topic)
    # returns straight away — the worker does the slow part
    job_id = await push_job(redis_client, config, req.topic, session_id, req.output_format)
    return {"job_id": job_id, "session_id": session_id}


@router.get("/result/{job_id}")
async def get_job_result(job_id: str):
    # client polls this. no result key yet = still working (or bad job_id).
    result = await get_result(get_redis(), config, job_id)
    if result is None:
        return {"status": "pending"}
    return result


@router.get("/result/{job_id}/pdf")
async def download_pdf(job_id: str):
    # lets you grab a pdf even if the job wasn't started with output_format=pdf
    result = await get_result(get_redis(), config, job_id)
    if not result or result.get("status") != "done":
        raise HTTPException(status_code=404, detail="Report not ready")
    # rendering happens in a thread so a long report doesn't stall the server
    pdf_bytes = await generate_pdf_async(result.get("topic", "Report"), result["report"])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={job_id}.pdf"},
    )


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    messages = await session_get(get_redis(), session_id)
    return {"session_id": session_id, "messages": messages}
