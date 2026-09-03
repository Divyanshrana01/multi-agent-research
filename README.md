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
- `terraform/main.tf` — infra: VPC, ECS Fargate, RDS Postgres, ElastiCache Redis,
  ALB, Bedrock Guardrail, Secrets Manager, ECR, weekly red-team EventBridge rule
- `bootstrap.sh` — one-time script to create the S3 bucket + DynamoDB table
  Terraform needs before it can run

## Next step

- Write `app/main.py` — the FastAPI entrypoint that wires config, db pool, cache,
  guardrails, queue, and the agent graph together
- Set up TensorZero locally (docker compose) so the agents have something to call
- Get infra actually deployed: `./bootstrap.sh` then `terraform init && terraform apply`
