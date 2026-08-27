# Multi-Agent Research Agent

An API that takes a research topic and returns a written, cited report.

A four-agent pipeline (search → summarise → write → critic) runs behind a job
queue, with caching, long-term memory, safety guardrails and an automated
red-team suite around it. Built to be measured at every step rather than
assembled from tutorials.

**Status:** Phase 0 — local stack and skeleton. See the phase list below.

---

## Running it locally

Requires Docker and Python 3.12.

```bash
cp .env.example .env
make up                                  # redis-stack + postgres/pgvector
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
make dev
```

Then:

```bash
curl localhost:8000/health
# {"status":"ok","redis":"ok","db":"ok"}
```

`make test` runs the unit tests (no containers needed), `make lint` runs ruff.

---

## Build phases

| Phase | What lands |
|---|---|
| 0 | Local stack, config, health check, test and lint setup |
| 1 | Single LLM call baseline, with latency and token cost measured |
| 2 | Locked golden set and LLM-as-judge evaluation harness |
| 3 | LangGraph multi-agent pipeline behind an LLM gateway |
| 4 | Real retrieval: web search, hybrid ranking, reranking, citations |
| 5 | Caching and memory: exact, semantic, session, long-term |
| 6 | Job queue, resilience, structured logging, stats |
| 7 | Guardrails and automated red teaming |
| 8 | Terraform on ECS Fargate with CI/CD and rollback |
| 9 | Measured results, architecture diagram, decision log |

Every phase after 1 is measured against the phase-1 baseline on the same locked
evaluation set. Anything that does not move the numbers comes back out.

---

## Design notes

Written up as the project goes: `DECISIONS.md` (why each component, and what was
rejected) and `LIMITATIONS.md` (what is weak and what I would do next).
