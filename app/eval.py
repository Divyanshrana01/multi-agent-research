# LLM-as-judge evaluation. After a report is written we ask the LLM to score it
# on four things (relevance, completeness, hallucination risk, overall quality)
# and push the scores to LangSmith so I can track quality over time.

import asyncio
import re
import httpx
import logging
from langsmith import Client, traceable
from app.config import Config
from app.retry import with_retry

logger = logging.getLogger(__name__)


_ls_client: Client | None = None


def _ls() -> Client:
    # built on first use and then reused, so importing this file doesn't
    # immediately need LangSmith credentials
    global _ls_client
    if _ls_client is None:
        _ls_client = Client()
    return _ls_client


def _parse_score(text: str) -> float:
    # judges are told to answer "SCORE: X/10", so pull that number out and turn
    # it into 0-1. If the LLM ignored the format we fall back to 0.5 rather than
    # crashing — a missing score shouldn't fail the whole job.
    m = re.search(r"SCORE:\s*(\d+(?:\.\d+)?)\s*/\s*10", text, re.IGNORECASE)
    return round(float(m.group(1)) / 10.0, 2) if m else 0.5


async def _judge(config: Config, prompt: str) -> str:
    # same pattern as the agents: lambda so each retry makes a fresh call
    return await with_retry(
        lambda: _judge_once(config, prompt),
        max_retries=config.llm_max_retries,
        delay=config.llm_retry_delay,
    )


async def _judge_once(config: Config, prompt: str) -> str:
    # goes through TensorZero like everything else, so judge calls show up in
    # the same place as the agent calls
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{config.tensorzero_url}/inference",
            json={
                "function_name": "research_summarize",
                "input": {"messages": [{"role": "user", "content": prompt}]},
            },
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"]


# The four judges below all follow the same shape: ask for a score out of 10,
# truncate the report so we don't blow the context window, and return a dict
# LangSmith can store. Higher is better for all of them EXCEPT hallucination.
@traceable(run_type="chain", name="eval:relevance")
async def eval_relevance(config: Config, topic: str, report: str) -> dict:
    verdict = await _judge(
        config,
        f"Rate how relevant this research report is to the topic '{topic}'.\n"
        f"Reply with exactly: SCORE: X/10 on the first line, then one sentence reason.\n\n"
        f"Report:\n{report[:config.eval_report_truncate]}",
    )
    return {"key": "relevance", "score": _parse_score(verdict), "comment": verdict[:config.eval_comment_truncate]}


@traceable(run_type="chain", name="eval:completeness")
async def eval_completeness(config: Config, report: str) -> dict:
    verdict = await _judge(
        config,
        f"Does this research report contain all four required sections: "
        f"Executive Summary, Key Findings, Analysis, and Conclusion?\n"
        f"Reply with exactly: SCORE: X/10 on the first line, then one sentence reason.\n\n"
        f"Report:\n{report[:config.eval_report_truncate]}",
    )
    return {"key": "completeness", "score": _parse_score(verdict), "comment": verdict[:config.eval_comment_truncate]}


# careful: this one is backwards on purpose — a LOW score is good here
@traceable(run_type="chain", name="eval:hallucination_risk")
async def eval_hallucination(config: Config, topic: str, report: str) -> dict:
    verdict = await _judge(
        config,
        f"Check this report on '{topic}' for hallucinations — fabricated statistics, "
        f"impossible dates, or claims that contradict well-known facts.\n"
        f"Score: 1/10 = zero hallucinations detected, 10/10 = many hallucinations.\n"
        f"Reply with exactly: SCORE: X/10 on the first line, then list any suspicious claims.\n\n"
        f"Report:\n{report[:config.eval_report_truncate]}",
    )
    return {"key": "hallucination_risk", "score": _parse_score(verdict), "comment": verdict[:config.eval_comment_truncate]}


@traceable(run_type="chain", name="eval:overall_quality")
async def eval_quality(config: Config, topic: str, report: str) -> dict:
    verdict = await _judge(
        config,
        f"Rate the overall quality of this research report on '{topic}'.\n"
        f"Consider: depth of analysis, factual accuracy, writing clarity, logical structure, "
        f"and practical usefulness to a business analyst.\n"
        f"Reply with exactly: SCORE: X/10 on the first line, then two sentences explaining the rating.\n\n"
        f"Report:\n{report[:config.eval_report_truncate]}",
    )
    return {"key": "overall_quality", "score": _parse_score(verdict), "comment": verdict[:config.eval_comment_truncate]}


@traceable(run_type="chain", name="evaluate-report")
async def evaluate_report(config: Config, job_id: str, topic: str, report: str) -> dict:
    """Runs all 4 LLM judges in parallel. Called on EVERY research job automatically."""
    # gather so the 4 judge calls happen at once instead of one after another
    results = await asyncio.gather(
        eval_relevance(config, topic, report),
        eval_completeness(config, report),
        eval_hallucination(config, topic, report),
        eval_quality(config, topic, report),
    )
    scores = {r["key"]: r["score"] for r in results}

    # everything below is just logging to LangSmith, so it's all wrapped in a
    # try/except — if LangSmith is down the user still gets their scores
    try:
        # the langsmith client is synchronous, so the whole write goes in one
        # thread rather than blocking the event loop on three HTTP calls
        await asyncio.to_thread(_log_to_langsmith, config, job_id, topic, report, scores)
    except Exception as e:
        logger.warning(f"LangSmith logging failed for job {job_id}: {e}")
    return scores


# blocking — only called through asyncio.to_thread above
def _log_to_langsmith(config: Config, job_id: str, topic: str, report: str, scores: dict) -> None:
    client = _ls()
    # no "create if missing" call in the API, so try to read it and make it
    # on the first run
    try:
        dataset = client.read_dataset(dataset_name=config.langsmith_dataset)
    except Exception:
        dataset = client.create_dataset(
            config.langsmith_dataset,
            description="Research agent LLM-as-judge evaluation results",
        )
    # scores go in metadata so I can filter/graph by them in the LangSmith UI
    client.create_example(
        inputs={"topic": topic},
        outputs={"report_preview": report[:400]},
        dataset_id=dataset.id,
        metadata={"job_id": job_id, **scores},
    )


async def fetch_recent_topics(limit: int = 10) -> list[str]:
    """Pull distinct topics from the reports table — real user queries, nothing hardcoded."""
    from app.pool import get_pool  # imported here to keep this module's import light
    pool = get_pool()
    async with pool.acquire() as conn:
        # GROUP BY dedupes topics that were asked more than once, and MAX(created_at)
        # sorts them by the most recent time each one came up
        rows = await conn.fetch(
            "SELECT topic FROM reports GROUP BY topic ORDER BY MAX(created_at) DESC LIMIT $1",
            limit,
        )
        return [row["topic"] for row in rows]


async def run_batch_evaluation(config: Config, graph, topics: list[str]) -> list[dict]:
    # re-runs the whole agent graph on a list of topics and scores each result.
    # used to check quality after changing a prompt or swapping models.
    from app.agents import ResearchState
    from app.memory import ltm_search_related
    results = []
    for topic in topics:
        # one bad topic shouldn't throw away the scores for all the others,
        # so each run is caught on its own and recorded as a failure
        try:
            # give the writer the same LTM context it would get on a real request,
            # otherwise the batch scores wouldn't match live behaviour
            ltm_context = await ltm_search_related(config, topic) or ""
            state = ResearchState(
                topic=topic, session_id="batch-eval",
                session_history=[],
                ltm_context=ltm_context,
                search_results=[], summaries=[], report="",
                verified=False, error="", iterations=0,
            )
            final = await graph.ainvoke(state)
            scores = await evaluate_report(config, f"batch-{topic[:20]}", topic, final["report"])
            results.append({"topic": topic, "scores": scores})
        except Exception as e:
            logger.error(f"Batch evaluation failed for topic '{topic}': {e}")
            results.append({"topic": topic, "error": str(e)})
    logger.info(f"Batch evaluation finished: {len(results)} topics")
    return results
