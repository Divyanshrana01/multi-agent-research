# One shared embedding model for the whole app. cache.py and memory.py both
# used to create their own SentenceTransformer, which loaded the same weights
# into memory twice. Loading it lazily also means importing these modules
# doesn't cost anything until something actually embeds text.

import asyncio
import threading
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # what all-MiniLM-L6-v2 outputs, matches vector(384) in the db

_model: SentenceTransformer | None = None
_lock = threading.Lock()


def get_model() -> SentenceTransformer:
    # double-checked locking so two threads starting at once don't both load it
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_sync(text: str) -> list[float]:
    """Blocking encode. Only call this from a thread, not the event loop."""
    return get_model().encode(text).tolist()


async def embed(text: str) -> list[float]:
    """Encode without blocking the event loop — this is what async code should use."""
    return await asyncio.to_thread(embed_sync, text)
