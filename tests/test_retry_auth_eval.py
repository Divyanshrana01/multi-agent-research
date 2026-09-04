# Tests for the small pieces everything else leans on: retry, auth, score
# parsing, and the report output helpers.

import pytest
from fastapi import HTTPException
from app import eval as evalmod
from app import output
from app.auth import require_api_key
from app.retry import with_retry


# ---------- retry ----------

@pytest.mark.asyncio
async def test_retry_returns_first_success():
    calls = []

    async def ok():
        calls.append(1)
        return "done"

    assert await with_retry(ok, max_retries=3, delay=0) == "done"
    assert len(calls) == 1  # no pointless second attempt


@pytest.mark.asyncio
async def test_retry_recovers_after_a_failure():
    calls = []

    async def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("boom")
        return "done"

    assert await with_retry(flaky, max_retries=3, delay=0) == "done"
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_retry_raises_the_last_error_when_all_attempts_fail():
    async def always_fails():
        raise ValueError("still broken")

    with pytest.raises(ValueError, match="still broken"):
        await with_retry(always_fails, max_retries=2, delay=0)


@pytest.mark.asyncio
async def test_retry_rejects_a_nonsense_retry_count():
    # with max_retries=0 the loop body never ran and the old code hit "raise None"
    async def noop():
        return None

    with pytest.raises(ValueError):
        await with_retry(noop, max_retries=0, delay=0)


# ---------- auth ----------

class FakeRequest:
    def __init__(self, headers: dict, api_key: str):
        self.headers = headers
        self.app = type("App", (), {"state": type("S", (), {"config": type("C", (), {"api_key": api_key})()})()})()


@pytest.mark.asyncio
async def test_auth_accepts_the_right_key():
    await require_api_key(FakeRequest({"X-API-Key": "secret"}, "secret"))


@pytest.mark.asyncio
async def test_auth_rejects_a_wrong_or_missing_key():
    for headers in ({"X-API-Key": "wrong"}, {}):
        with pytest.raises(HTTPException) as exc:
            await require_api_key(FakeRequest(headers, "secret"))
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_is_off_when_no_key_is_configured():
    # local runs without an API key set should not be locked out
    await require_api_key(FakeRequest({}, ""))


# ---------- judge score parsing ----------

@pytest.mark.parametrize("text,expected", [
    ("SCORE: 8/10\nGood coverage.", 0.8),
    ("score: 10/10", 1.0),
    ("SCORE: 7.5/10", 0.75),
    ("SCORE:3 / 10", 0.3),
    ("The report was fine.", 0.5),   # judge ignored the format, fall back
    ("", 0.5),
])
def test_parse_score(text, expected):
    assert evalmod._parse_score(text) == pytest.approx(expected)


# ---------- report output ----------

def test_json_report_counts_words_and_checksums():
    result = output.generate_json_report("topic", "one two three", "id-1", _now())
    assert result["word_count"] == 3
    assert result["report_id"] == "id-1"
    assert len(result["checksum"]) == 32


def test_json_checksum_changes_with_the_report():
    a = output.generate_json_report("t", "first version", "id", _now())
    b = output.generate_json_report("t", "second version", "id", _now())
    assert a["checksum"] != b["checksum"]


def test_pdf_is_a_real_pdf():
    data = output.generate_pdf("A title", "Body text\n" * 200)  # long enough to paginate
    assert data.startswith(b"%PDF")
    assert len(data) > 1000


def test_pdf_handles_empty_content():
    assert output.generate_pdf("Title", "").startswith(b"%PDF")


@pytest.mark.asyncio
async def test_pdf_async_matches_the_sync_version():
    data = await output.generate_pdf_async("Title", "Body")
    assert data.startswith(b"%PDF")


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
