# Build from the repo root:
#   docker build -t research-agent .
#
# Two stages: node builds the frontend, python serves it alongside the API.
# Only the built assets cross over, so node and node_modules never ship.

# ---------- stage 1: frontend ----------
FROM node:22-slim AS frontend
WORKDIR /build

# package files first, so a source-only change doesn't reinstall everything
COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ---------- stage 2: api ----------
FROM python:3.12-slim
WORKDIR /app

# gcc and libpq-dev are needed to build the postgres driver. deleting the apt
# lists in the same RUN keeps them out of the image layer.
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# run as a normal user instead of root, so a bug in the app can't rewrite the
# image. created before the model download so the cache lands in its home dir.
RUN useradd --create-home --uid 1000 appuser
ENV HOME=/home/appuser

# requirements on its own layer, so docker only redoes the slow pip install
# when the requirements change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# download the embedding model at build time so it's baked into the image.
# otherwise the first request after every deploy pays for the download.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" \
    && chown -R appuser:appuser /home/appuser

# model is already local, so don't let it call huggingface at runtime.
# PYTHONUNBUFFERED keeps logs flowing to CloudWatch instead of sitting in a buffer.
ENV HF_HUB_OFFLINE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# app code and built frontend last, because they change the most
COPY --chown=appuser:appuser app/ ./app/
COPY --from=frontend --chown=appuser:appuser /build/dist ./frontend/dist

USER appuser

EXPOSE 8000

# the load balancer has its own check, this one is for docker/compose runs
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# 0.0.0.0 so the container is reachable from outside, not just from inside itself.
# --proxy-headers makes uvicorn trust X-Forwarded-For from the load balancer,
# which is what the per-IP rate limiter reads.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
