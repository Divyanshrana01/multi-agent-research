# Tests for the API layer: request validation and how the rate limiter works
# out who is calling. Importing these modules only works offline because
# conftest sets LOCAL_CONFIG=1.

import pytest
from pydantic import ValidationError
from app.api.schemas import ResearchRequest, BatchEvalRequest
from app.runtime import client_ip


class FakeRequest:
    def __init__(self, headers=None, host="10.0.0.1"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": host})() if host else None


# ---------- request validation ----------

def test_research_request_defaults():
    req = ResearchRequest(topic="quantum computing")
    assert req.output_format == "text"
    assert req.session_id == ""


@pytest.mark.parametrize("topic", ["", "ab", "x" * 501])
def test_research_request_rejects_bad_topics(topic):
    # too short is usually a mis-click, too long is someone pasting a document
    with pytest.raises(ValidationError):
        ResearchRequest(topic=topic)


def test_research_request_rejects_an_unknown_format():
    # this used to sail through and silently fall back to plain text
    with pytest.raises(ValidationError):
        ResearchRequest(topic="quantum computing", output_format="xml")


@pytest.mark.parametrize("fmt", ["text", "pdf", "json"])
def test_research_request_accepts_supported_formats(fmt):
    assert ResearchRequest(topic="quantum computing", output_format=fmt).output_format == fmt


def test_batch_eval_caps_the_topic_list():
    # each topic is a full pipeline run plus four judge calls
    BatchEvalRequest(topics=["t"] * 20)
    with pytest.raises(ValidationError):
        BatchEvalRequest(topics=["t"] * 21)


def test_batch_eval_defaults_to_empty():
    assert BatchEvalRequest().topics == []


# ---------- client ip ----------

def test_client_ip_prefers_the_forwarded_header():
    # behind the ALB, request.client.host is the balancer, so without this every
    # user would share a single rate limit bucket
    request = FakeRequest({"X-Forwarded-For": "203.0.113.7"}, host="10.0.0.1")
    assert client_ip(request) == "203.0.113.7"


def test_client_ip_takes_the_original_client_from_a_chain():
    request = FakeRequest({"X-Forwarded-For": "203.0.113.7, 70.41.3.18, 10.0.0.1"})
    assert client_ip(request) == "203.0.113.7"


def test_client_ip_falls_back_to_the_socket():
    assert client_ip(FakeRequest(host="192.0.2.5")) == "192.0.2.5"


def test_client_ip_handles_no_client_at_all():
    # happens for lifespan/test transports rather than real requests
    assert client_ip(FakeRequest(host=None)) == "unknown"
