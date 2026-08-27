.PHONY: up down dev test lint fmt

up:
	docker compose up -d

down:
	docker compose down

dev:
	uvicorn app.main:app --reload --port 8000

test:
	pytest -q

lint:
	ruff check .

fmt:
	ruff format .
