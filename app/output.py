# Turns a finished report into whatever format the user asked for (pdf or json),
# plus a diff view showing what changed between the last two reports on a topic.

import asyncio
import difflib
import hashlib
from datetime import datetime
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from app.config import Config
from app.embeddings import embed
from app.pool import get_pool


def generate_pdf(title: str, content: str) -> bytes:
    # build the pdf in memory instead of writing a temp file, so we can just
    # return the bytes straight to the API response
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    _, height = A4  # only the height matters, we position from the top down
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, title[:80])  # cut long titles so they fit one line
    c.setFont("Helvetica", 10)

    # y is how far up the page we are, and it counts down as we add lines
    y = height - 80
    for line in content.split("\n"):
        # drawString doesn't wrap text, so split long lines into 95-char chunks ourselves
        for chunk in [line[i:i + 95] for i in range(0, max(len(line), 1), 95)]:
            if y < 60:  # near the bottom, start a new page
                c.showPage()
                y = height - 50
            c.drawString(50, y, chunk)
            y -= 14
    c.save()
    buffer.seek(0)
    return buffer.read()


# async wrapper for the above. rendering a long report takes long enough to
# stall every other request, so it runs in a thread.
async def generate_pdf_async(title: str, content: str) -> bytes:
    return await asyncio.to_thread(generate_pdf, title, content)


def generate_json_report(topic: str, report: str, report_id: str, created_at: datetime) -> dict:
    # checksum lets a caller tell if two reports are byte-for-byte the same
    # without comparing the whole text (md5 is fine here, it's not for security)
    return {
        "report_id": report_id,
        "topic": topic,
        "report": report,
        "created_at": created_at.isoformat(),
        "word_count": len(report.split()),
        "checksum": hashlib.md5(report.encode()).hexdigest(),
    }


async def get_report_diff(config: Config, topic: str) -> str | None:
    # encoding is CPU work, so it runs in a thread (see embeddings.py)
    embedding = await embed(topic)
    pool = get_pool()
    async with pool.acquire() as conn:
        # <=> is pgvector's cosine distance, so 1 - distance = similarity.
        # grabs the two newest reports that are close enough to this topic.
        rows = await conn.fetch(
            """
            SELECT report, created_at FROM reports
            WHERE 1 - (embedding <=> $1::vector) > $2
            ORDER BY created_at DESC LIMIT 2
            """,
            str(embedding), config.ltm_diff_threshold,
        )
        if len(rows) < 2:
            return None  # nothing to compare against yet
        # rows are newest first, so row 1 is the older report and row 0 the newer one
        old_lines = rows[1]["report"].splitlines(keepends=True)
        new_lines = rows[0]["report"].splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"previous ({rows[1]['created_at'].date()})",
            tofile=f"latest ({rows[0]['created_at'].date()})",
            lineterm="",
        ))
        if not diff_lines:
            return "No significant changes since last report."
        # cap the output so a big rewrite doesn't dump a huge diff on the user
        return "\n".join(diff_lines[:config.ltm_diff_limit * 10])
