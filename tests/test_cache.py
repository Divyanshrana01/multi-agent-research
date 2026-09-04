# Tests for the semantic cache. The embedding model is swapped out for a fake
# one so these run in milliseconds and don't depend on model weights.

import json
import numpy as np
import pytest
from app import cache


class FakeRedis:
    """Just enough redis to exercise cache_get/cache_set."""

    def __init__(self, data: dict | None = None):
        self.data = data or {}

    async def scan_iter(self, match: str):
        prefix = match.rstrip("*")
        for key in list(self.data):
            if key.startswith(prefix):
                yield key

    async def mget(self, keys):
        return [self.data.get(k) for k in keys]

    async def get(self, key):
        return self.data.get(key)

    def pipeline(self, transaction=True):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis: FakeRedis):
        self.redis = redis
        self.ops = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def setex(self, key, ttl, value):
        self.ops.append((key, value))

    async def execute(self):
        for key, value in self.ops:
            self.redis.data[key] = value
        return [True] * len(self.ops)


def test_key_suffix_is_stable_across_processes():
    # the bug this guards: python's built-in hash() is salted per process, so
    # every worker produced a different key for the same question
    assert cache._key_suffix("quantum computing") == cache._key_suffix("quantum computing")
    assert cache._key_suffix("a") != cache._key_suffix("b")
    assert len(cache._key_suffix("anything")) == 16


def test_as_str_handles_bytes_and_str():
    assert cache._as_str(b"hello") == "hello"
    assert cache._as_str("hello") == "hello"


def test_cosine_similarity_identical_and_orthogonal():
    stored = np.array([[1.0, 0.0], [0.0, 1.0]])
    scores = cache._cosine_similarities([1.0, 0.0], stored)
    assert scores[0] == pytest.approx(1.0)
    assert scores[1] == pytest.approx(0.0)


def test_cosine_similarity_survives_a_zero_vector():
    # a zero vector would divide by zero without the guard in _cosine_similarities
    scores = cache._cosine_similarities([1.0, 0.0], np.array([[0.0, 0.0]]))
    assert np.isfinite(scores).all()


@pytest.mark.asyncio
async def test_cache_get_returns_none_when_empty(config, monkeypatch):
    monkeypatch.setattr(cache, "embed", _fake_embed)
    assert await cache.cache_get(FakeRedis(), config, "anything") is None


@pytest.mark.asyncio
async def test_cache_set_then_get_round_trip(config, monkeypatch):
    monkeypatch.setattr(cache, "embed", _fake_embed)
    redis = FakeRedis()
    await cache.cache_set(redis, config, "quantum computing", "the answer")
    assert await cache.cache_get(redis, config, "quantum computing") == "the answer"


@pytest.mark.asyncio
async def test_cache_get_misses_when_below_threshold(config, monkeypatch):
    monkeypatch.setattr(cache, "embed", _fake_embed)
    redis = FakeRedis()
    await cache.cache_set(redis, config, "quantum computing", "the answer")
    # a completely different question embeds to an orthogonal vector
    assert await cache.cache_get(redis, config, "banana bread") is None


@pytest.mark.asyncio
async def test_cache_get_skips_embeddings_of_a_different_length(config, monkeypatch):
    # left over from an older model, these used to crash numpy with a ragged array
    monkeypatch.setattr(cache, "embed", _fake_embed)
    redis = FakeRedis({f"{cache._EMB_PREFIX}stale": json.dumps([0.1] * 7)})
    assert await cache.cache_get(redis, config, "quantum computing") is None


@pytest.mark.asyncio
async def test_cache_get_handles_an_expired_answer(config, monkeypatch):
    # the embedding can outlive its answer if the two keys expire a moment apart
    monkeypatch.setattr(cache, "embed", _fake_embed)
    redis = FakeRedis()
    await cache.cache_set(redis, config, "quantum computing", "the answer")
    del redis.data[f"{cache._CACHE_PREFIX}{cache._key_suffix('quantum computing')}"]
    assert await cache.cache_get(redis, config, "quantum computing") is None


async def _fake_embed(text: str) -> list[float]:
    """Deterministic stand-in: same text -> same vector, different text -> orthogonal."""
    vectors = {
        "quantum computing": [1.0, 0.0, 0.0],
        "banana bread": [0.0, 1.0, 0.0],
    }
    return vectors.get(text, [0.0, 0.0, 1.0])
