"""One browser manager, rate limiter, and request admission per process."""

import logging
from slowapi import Limiter
from slowapi.util import get_remote_address

from .browser import WebHookBrowserManager
from .accounts import AccountManager
from .config import (
    ACCOUNTS_STATE_PATH, CHROME_PROFILE_DIR, TARGET_URL,
    CHROME_PROFILES_LIST, VIREL_GOOGLE_ACCOUNTS_COUNT, VIREL_ACCOUNT_COOLDOWN_SECONDS
)
from .config import (MAX_CONCURRENT, MAX_QUEUE, QUEUE_TIMEOUT_SECONDS, MEMORY_RESERVE_MB, TAB_MEMORY_MB, MAX_WAITING_TABS)
from .browser_pool import BrowserPool, BrowserAdmission

logger = logging.getLogger("virel.webhook")
account_manager = AccountManager(
    state_path=ACCOUNTS_STATE_PATH,
    default_profile_dir=CHROME_PROFILE_DIR,
    target_base_url=TARGET_URL,
    profiles_list=CHROME_PROFILES_LIST,
    authuser_count=VIREL_GOOGLE_ACCOUNTS_COUNT,
    cooldown_seconds=VIREL_ACCOUNT_COOLDOWN_SECONDS,
)
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
