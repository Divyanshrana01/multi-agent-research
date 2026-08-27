# Multi-Agent AI Research Platform

A research agent backend: FastAPI + LangGraph agents, TensorZero as the LLM gateway,
Redis for semantic cache/session/queue, Postgres (pgvector) for long-term memory,
AWS Bedrock Guardrails for content safety, deployed on ECS Fargate via Terraform.

## Progress so far

- `app/config.py` — loads all settings from AWS Secrets Manager, cached after first call
- `app/pool.py` — async Postgres connection pool (init/get/close)
- `app/retry.py` — retry helper with exponential backoff for flaky calls
- `terraform/main.tf` — infra: VPC, ECS Fargate, RDS Postgres, ElastiCache Redis,
  ALB, Bedrock Guardrail, Secrets Manager, ECR, weekly red-team EventBridge rule
- `bootstrap.sh` — one-time script to create the S3 bucket + DynamoDB table
  Terraform needs before it can run

## Next step

- Write `app/main.py` — the FastAPI entrypoint that wires config, db pool, and
  the LangGraph agent graph together
- Get infra actually deployed: `./bootstrap.sh` then `terraform init && terraform apply`
- Add the LangGraph agent nodes and the TensorZero gateway sidecar
