import hashlib
import json
import numpy as np
import redis.asyncio as aioredis
from app.config import Config
from app.embeddings import embed

# the embedding model itself lives in app/embeddings.py so the whole app shares
# one copy. similar sentences get similar numbers, that's the whole trick here.

# we store two things in redis per cached query, so two key prefixes:
# "semantic:" holds the actual answer, "emb:" holds the embedding of the question
_CACHE_PREFIX = "semantic:"
_EMB_PREFIX = "emb:"


# redis hands back bytes unless the client was made with decode_responses=True,
# so this makes sure we always end up with a normal string either way
def _as_str(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


# compares our one question against ALL stored questions in one go
# doing it as a matrix is way faster than looping one by one in python
# returns a score per stored question, 1.0 = identical, 0 = nothing in common
def _cosine_similarities(query_emb: list, stored: np.ndarray) -> np.ndarray:
    q = np.array(query_emb)
    denom = np.linalg.norm(stored, axis=1) * np.linalg.norm(q)
    denom[denom == 0] = 1e-9  # don't divide by zero if some vector is all zeros
    return stored @ q / denom


# builds the redis key for a query
# sha256 instead of python's hash() because hash() gives a DIFFERENT number
# every time python restarts, so each worker would save its own duplicate copy
def _key_suffix(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()[:16]


# looks for an old answer to a question that MEANS the same thing as this one
# (not just exact same text) - saves us paying for the same llm call twice
async def cache_get(redis: aioredis.Redis, config: Config, query: str) -> str | None:
    # embed the new question so we can compare it to old ones.
    # awaited because encoding is CPU work that would otherwise block every
    # other request while it runs.
    query_emb = await embed(query)

    # grab the names of every stored embedding
    keys = [_as_str(key) async for key in redis.scan_iter(f"{_EMB_PREFIX}*")]
    if not keys:
        return None

    # fetch them all in ONE call instead of one call per key
    raw = await redis.mget(keys)

    # a key can expire in the gap between listing it and fetching it,
    # so drop anything that came back empty
    found = [(key, json.loads(value)) for key, value in zip(keys, raw) if value is not None]
    if not found:
        return None

    # a stored embedding from an older model version would have a different
    # length and break the matrix, so only compare ones that still match
    usable = [(key, vec) for key, vec in found if len(vec) == len(query_emb)]
    if not usable:
        return None

    # score every stored question at once, then take the closest one
    scores = _cosine_similarities(query_emb, np.array([vec for _, vec in usable]))
    best = int(np.argmax(scores))

    # closest one still isn't close enough? then we've never really been asked this
    if scores[best] < config.cache_similarity_threshold:
        return None

    # swap the prefix to find the answer that goes with this embedding.
    # slicing rather than .replace() so we only touch the prefix.
    cache_key = _CACHE_PREFIX + usable[best][0][len(_EMB_PREFIX):]
    answer = await redis.get(cache_key)
    # the answer could have expired too, even though its embedding survived
    return _as_str(answer) if answer is not None else None


# saves a question + its answer so next time a similar question can reuse it
async def cache_set(redis: aioredis.Redis, config: Config, query: str, result: str) -> None:
    # same id for both keys (answer + embedding) so they stay paired up
    suffix = _key_suffix(query)
    query_emb = await embed(query)
    # setex = save with an expiry time, so old stuff clears itself out.
    # pipeline so both keys are written in one round trip and neither can be
    # left behind on its own.
    async with redis.pipeline(transaction=True) as pipe:
        pipe.setex(f"{_CACHE_PREFIX}{suffix}", config.cache_ttl, result)
        pipe.setex(f"{_EMB_PREFIX}{suffix}", config.cache_ttl, json.dumps(query_emb))
        await pipe.execute()
