import json
import numpy as np
import redis.asyncio as aioredis
from sentence_transformers import SentenceTransformer
from app.config import Config

# small local model that turns text into a list of numbers (an "embedding")
# similar sentences end up with similar numbers, that's the whole trick here
_model = SentenceTransformer("all-MiniLM-L6-v2")
# we store two things in redis per cached query, so two key prefixes:
# "semantic:" holds the actual answer, "emb:" holds the embedding of the question
_CACHE_PREFIX = "semantic:"
_EMB_PREFIX = "emb:"


# measures how similar two embeddings are, 1.0 = identical, 0 = nothing in common
def _cosine_similarity(a: list, b: list) -> float:
    va, vb = np.array(a), np.array(b)
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))


# turns a piece of text into its embedding (list of numbers)
def _embed(text: str) -> list:
    return _model.encode(text).tolist()


# looks for an old answer to a question that MEANS the same thing as this one
# (not just exact same text) - saves us paying for the same llm call twice
async def cache_get(redis: aioredis.Redis, config: Config, query: str) -> str | None:
    # embed the new question so we can compare it to old ones
    query_emb = _embed(query)
    # walk through every stored embedding in redis
    async for key in redis.scan_iter(f"{_EMB_PREFIX}*"):
        stored_emb = json.loads(await redis.get(key))
        # close enough? then we already answered basically this question before
        if _cosine_similarity(query_emb, stored_emb) >= config.cache_similarity_threshold:
            # swap the prefix to find the answer that goes with this embedding
            cache_key = key.replace(_EMB_PREFIX, _CACHE_PREFIX)
            return await redis.get(cache_key)
    # nothing similar found, caller will have to actually run the llm
    return None


# saves a question + its answer so next time a similar question can reuse it
async def cache_set(redis: aioredis.Redis, config: Config, query: str, result: str) -> None:
    # make an id for this query so both keys (answer + embedding) match up
    key_suffix = abs(hash(query))
    # setex = save with an expiry time, so old stuff clears itself out
    await redis.setex(f"{_CACHE_PREFIX}{key_suffix}", config.cache_ttl, result)
    await redis.setex(f"{_EMB_PREFIX}{key_suffix}", config.cache_ttl, json.dumps(_embed(query)))
