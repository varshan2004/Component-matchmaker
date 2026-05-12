"""
scrapers/retry.py — Simple async retry wrapper.
Retries once after 1s on network errors / 5xx responses.
"""

import asyncio
import httpx


async def with_retry(fn, *args, retries: int = 1, delay: float = 1.0, **kwargs):
    """
    Call fn(*args, **kwargs). On httpx network/server error,
    wait `delay` seconds and retry up to `retries` times.
    Returns {} on final failure — never raises.
    """
    for attempt in range(retries + 1):
        try:
            result = await fn(*args, **kwargs)
            return result
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            if attempt < retries:
                print(f"[retry] {fn.__name__} failed ({e}), retrying in {delay}s…")
                await asyncio.sleep(delay)
            else:
                print(f"[retry] {fn.__name__} failed after {retries+1} attempts: {e}")
                return {}
        except Exception as e:
            print(f"[retry] {fn.__name__} unexpected error: {e}")
            return {}
    return {}