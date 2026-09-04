# FastAPI entrypoint. This file only wires things together now — the endpoints
# live in app/api/, the background worker in app/worker.py, and the frontend
# serving in app/spa.py.
#
# The shape of a request: /api/research drops a job on the redis stream and
# returns a job_id straight away, the worker in this same process picks it up,
# and the client polls /api/result/{job_id} until it's done.

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis

# logging is set up before the app imports below on purpose, so every module's
# logger picks up this json format. that's why these imports aren't all at the top.
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)

from app.runtime import config, spawn, set_runtime, clear_runtime
from app.pool import init_pool, close_pool
from app.memory import db_migrate
from app.agents import build_graph
from app.worker import worker_loop
from app.api import api_router, health_router
from app.spa import mount_frontend


@asynccontextmanager
async def lifespan(app: FastAPI):
    # everything before the yield runs on startup, everything after on shutdown.
    # order matters: connections and tables first, then the graph, then the worker.
    redis_client = await aioredis.from_url(config.redis_url, decode_responses=True)
    await init_pool(config)
    await db_migrate(config)  # creates the reports table/indexes if they don't exist
    graph = build_graph(config)
    # hand both to app/runtime.py so the routers and the worker can reach them
    set_runtime(redis_client, graph)
    worker = spawn(worker_loop(), "worker-loop")  # runs in the same process as the API
    logger.info("Startup complete")

    yield

    # stop the worker before tearing down its connections, otherwise it wakes
    # up mid-shutdown and logs errors about a closed redis client
    worker.cancel()
    try:
        await worker
    except asyncio.CancelledError:
        pass
    await redis_client.aclose()
    await close_pool()
    clear_runtime()
    logger.info("Shutdown complete")


app = FastAPI(title="Research Agent API", lifespan=lifespan)
# set here rather than inside lifespan, because require_api_key reads it. if it
# only existed after startup, any request arriving during a failed or partial
# startup would raise AttributeError instead of a clean 401.
app.state.config = config

# in dev the frontend runs on vite's own port (5173) and calls this server, so
# it needs CORS. in production both come from this origin and it's unused.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(api_router)

# always last: the catch-all inside would otherwise swallow the routes above
mount_frontend(app)
