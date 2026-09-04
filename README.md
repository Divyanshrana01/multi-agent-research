# Multi-Agent AI Research Platform

A research agent backend: FastAPI + LangGraph agents, TensorZero as the LLM gateway,
Redis for semantic cache/session/queue, Postgres (pgvector) for long-term memory,
AWS Bedrock Guardrails for content safety, deployed on ECS Fargate via Terraform.

## Progress so far

- `app/config.py` — loads all settings from AWS Secrets Manager, cached after first call
- `app/pool.py` — async Postgres connection pool (init/get/close)
- `app/retry.py` — retry helper with exponential backoff for flaky calls
- `app/auth.py` — API key check on incoming requests
- `app/guardrails.py` — Bedrock Guardrails check on both the question and the answer
- `app/cache.py` — semantic cache in Redis, reuses an answer if a similar question was asked before
- `app/memory.py` — short-term chat history (Redis) and long-term report storage (Postgres + pgvector)
- `app/queue.py` — Redis Streams job queue so requests can be handled by a worker instead of inline
- `app/agents.py` — the four LangGraph agents (search, summarize, write, critic) and the graph
  that wires them together, looping back through the critic
- `app/eval.py` — LLM-as-judge scoring (relevance, completeness, hallucination risk,
  overall quality), logged to LangSmith on every job
- `app/output.py` — PDF and structured-JSON exports, plus diffing the last two reports
- `app/embeddings.py` — one shared embedding model for the cache and long-term memory
- `app/main.py` — the FastAPI entrypoint: `/research` queues a job and returns a job id,
  a background worker runs the pipeline, the client polls `/result/{job_id}`
- `frontend/` — React + TypeScript app (Vite): the live pipeline, a browsable report
  library, judge scores, and Redis stats. Light and dark themes.
- `terraform/main.tf` — infra: VPC, ECS Fargate, RDS Postgres, ElastiCache Redis,
  ALB, Bedrock Guardrail, Secrets Manager, ECR, weekly red-team EventBridge rule
- `bootstrap.sh` — one-time script to create the S3 bucket + DynamoDB table
  Terraform needs before it can run

## API

Everything lives under `/api`, so the frontend's own routes (`/reports`,
`/settings`) don't collide with it. `/health` stays at the root for the load
balancer, and any other path returns the app shell for client-side routing.

| Endpoint | What it does |
| --- | --- |
| `POST /api/research` | Queues a job, returns a `job_id` immediately |
| `GET /api/result/{job_id}` | Poll until `status` leaves `pending` |
| `GET /api/reports` | Newest report per topic, keyset paginated |
| `GET /api/reports/{id}` | One report with its diff |
| `GET /api/session/{id}` | Short-term chat history |
| `GET /api/stats` | Redis figures for the dashboard |
| `GET /api/evaluate/{job_id}` | Re-scores a report with the four judges |
| `GET /health` | Redis + Postgres check, no auth |

## Running it locally

Settings normally come from AWS Secrets Manager. `LOCAL_CONFIG=1` reads them from
environment variables instead, so no AWS account is needed to run or test:

```bash
# terminal 1 — API
export LOCAL_CONFIG=1
export REDIS_URL="redis://localhost:6379"
export DATABASE_URL="postgresql://localhost/research"
export TENSORZERO_URL="http://localhost:3000"

pytest                                  # offline, no services required
uvicorn app.main:app --reload           # needs Redis + Postgres running

# terminal 2 — frontend, proxying /api to the above
cd frontend
npm install
npm run dev                             # http://localhost:5173
npm test                                # offline
```

Production shape is a single container — the Dockerfile builds the frontend in a
node stage and FastAPI serves the result:

```bash
docker build -t research-agent .
docker run -p 8000:8000 --env-file .env research-agent
```

## Next step

- Set up TensorZero locally (docker compose) so the agents have something to call
- Get infra actually deployed: `./bootstrap.sh` then `terraform init && terraform apply`
