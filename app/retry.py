import asyncio
import logging

logger = logging.getLogger(__name__)


# this function tries to call coro_fn and if it fails, waits a bit and tries again
# wait time doubles (backoff) each retry so we don't spam whatever we're calling
async def with_retry(coro_fn, max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Call coro_fn() with exponential backoff. Raises the last exception if all retries fail."""
    if max_retries < 1:
        # otherwise the loop never runs and we'd fall through to "raise None"
        raise ValueError("max_retries must be at least 1")

    last_exc = None  # keep track of the last error so we can raise it if everything fails
    wait = delay  # how long to sleep before next retry, grows every attempt
    for attempt in range(1, max_retries + 1):
        try:
            # try running the actual function, if it works just return the result
            return await coro_fn()
        except Exception as exc:
            # save the error and log it, then wait before retrying
            last_exc = exc
            if attempt < max_retries:
                logger.warning(f"Attempt {attempt}/{max_retries} failed: {exc}. Retrying in {wait:.1f}s")
                await asyncio.sleep(wait)
                wait *= backoff  # next wait is longer (exponential backoff)
    # if we got here, every attempt failed, so raise the last error we saw
    raise last_exc
