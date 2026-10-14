"""One browser manager, rate limiter, and admission semaphore per process."""

import asyncio
import logging
from typing import Optional
from slowapi import Limiter
from slowapi.util import get_remote_address

from .browser import WebHookBrowserManager
from .config import MAX_CONCURRENT

logger = logging.getLogger("virel.webhook")
browser_manager = WebHookBrowserManager()
limiter = Limiter(key_func=get_remote_address)
_semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        logger.info(f"Concurrency semaphore initialized: max {MAX_CONCURRENT} simultaneous requests")
    return _semaphore
