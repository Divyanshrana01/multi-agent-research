# Browsing reports that were already written, and diffing a topic against its
# previous version.

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import require_api_key
from app.runtime import config
from app.memory import list_reports, get_report, ltm_diff
from app.output import get_report_diff

router = APIRouter(tags=["reports"], dependencies=[Depends(require_api_key)])


@router.get("/reports")
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


@router.get("/reports/{report_id}")
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


@router.get("/diff/{topic}")
async def report_diff(topic: str):
    diff = await get_report_diff(config, topic)
    return {"topic": topic, "diff": diff or "No previous report found."}
