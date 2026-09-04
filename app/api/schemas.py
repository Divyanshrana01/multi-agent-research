# Request bodies for the API. Pydantic checks these before anything reaches
# redis or an LLM, so bad input costs us nothing.

from typing import Literal
from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    # pydantic rejects junk before it reaches redis or an LLM: an empty topic,
    # a novel pasted into the box, or a made-up output format
    topic: str = Field(min_length=3, max_length=500)
    session_id: str = Field(default="", max_length=100)
    output_format: Literal["text", "pdf", "json"] = "text"


class BatchEvalRequest(BaseModel):
    # capped because every topic here is a full pipeline run plus 4 judge calls
    topics: list[str] = Field(default_factory=list, max_length=20)
