from __future__ import annotations

import asyncio
import logging
from typing import Any

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)


log = logging.getLogger("search")

_SEARCH_SEMAPHORE = asyncio.Semaphore(1)
_TRANSIENT_MARKERS = (
    "429",
    "too many requests",
    "rate limit",
    "rate limited",
    "503",
    "502",
    "504",
    "temporarily unavailable",
    "timeout",
    "timed out",
    "connection reset",
    "connection aborted",
    "fetch failed",
    "server disconnected",
)


def _walk_exception_chain(exc: BaseException) -> list[BaseException]:
    seen: set[int] = set()
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def is_transient_search_error(exc: BaseException) -> bool:
    for current in _walk_exception_chain(exc):
        parts = [str(current)]
        message = getattr(current, "message", None)
        body = getattr(current, "body", None)
        if isinstance(message, str):
            parts.append(message)
        if isinstance(body, str):
            parts.append(body)
        text = "\n".join(parts).lower()
        if any(marker in text for marker in _TRANSIENT_MARKERS):
            return True
    return False


@retry(
    retry=retry_if_exception(is_transient_search_error),
    wait=wait_random_exponential(multiplier=2, max=60),
    stop=stop_after_attempt(5),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)
async def run_search_backed_agent(
    agent: Any,
    prompt: str,
    *,
    usage_limits: Any = None,
) -> Any:
    async with _SEARCH_SEMAPHORE:
        return await agent.run(prompt, usage_limits=usage_limits)
