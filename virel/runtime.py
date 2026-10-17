"""One browser manager, rate limiter, and request admission per process."""

import logging
from slowapi import Limiter
from slowapi.util import get_remote_address

from .browser import WebHookBrowserManager
from .config import (MAX_CONCURRENT, MAX_QUEUE, QUEUE_TIMEOUT_SECONDS, MEMORY_RESERVE_MB, TAB_MEMORY_MB, MAX_WAITING_TABS)
from .browser_pool import BrowserPool, BrowserAdmission

logger = logging.getLogger("virel.webhook")
browser_manager = BrowserPool(WebHookBrowserManager(), max_active=MAX_CONCURRENT, max_queue=MAX_QUEUE,
    timeout=QUEUE_TIMEOUT_SECONDS, reserve_mb=MEMORY_RESERVE_MB, tab_mb=TAB_MEMORY_MB, max_waiting=MAX_WAITING_TABS)
limiter = Limiter(key_func=get_remote_address)
_semaphore = None


def _get_semaphore():
    global _semaphore
    if _semaphore is None:
        _semaphore = BrowserAdmission(browser_manager)
        logger.info(f"Browser admission initialized: max {MAX_CONCURRENT} simultaneous requests")
    return _semaphore
