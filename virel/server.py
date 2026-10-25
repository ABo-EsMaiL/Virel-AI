"""FastAPI composition and startup/shutdown; no request transformations here."""

import asyncio
import logging
import os
from contextlib import suppress
from .files import prune_files, expiry_loop
from .browser_pool import BrowserRequestMiddleware
from json import JSONDecodeError
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from .images import MAX_REQUEST_BYTES
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from .errors import GatewayError, http_error_handler, validation_error_handler, rate_limit_handler
from slowapi.errors import RateLimitExceeded

from .config import DEFAULT_MODEL, THINKING_MODE, CHROME_PROFILE_DIR, HEADLESS, PORT, MAX_CONCURRENT, RATE_LIMIT, ALLOWED_PUBLIC_HOSTS, PUBLIC_URL, ACTIVE_PUBLIC_URL
from .runtime import browser_manager, limiter, _get_semaphore
from .routes import chat, responses, completions, system, files, audio, image_generation, anthropic, mcp, dashboard_api

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("virel.webhook")

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0", "host.docker.internal", "testserver", "testclient", ""}

def _extract_hostname(raw_header: str) -> str:
    first = raw_header.split(",")[0].strip().lower()
    if not first:
        return ""
    if first.startswith("["):
        return first.split("]")[0] + "]"
    return first.split(":")[0]

class PublicUrlAllowlistMiddleware:
    """Allow localhost always; allow external hosts only if listed in VIREL_PUBLIC_URL."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        raw_host = headers.get(b"host", b"").decode("latin1")
        raw_fwd_host = headers.get(b"x-forwarded-host", b"").decode("latin1")
        host_name = _extract_hostname(raw_host)
        fwd_name = _extract_hostname(raw_fwd_host)

        matched_public = PUBLIC_URL
        for candidate in (fwd_name, host_name):
            if not candidate or candidate in LOCAL_HOSTS:
                continue
            if candidate not in ALLOWED_PUBLIC_HOSTS:
                response = await http_error_handler(
                    Request(scope),
                    GatewayError(
                        403,
                        f"Untrusted external host '{candidate}'. Add this domain to VIREL_PUBLIC_URL in .env to allow external access.",
                        "untrusted_host"
                    )
                )
                return await response(scope, receive, send)
            matched_public = ALLOWED_PUBLIC_HOSTS[candidate]

        token = ACTIVE_PUBLIC_URL.set(matched_public)
        try:
            await self.app(scope, receive, send)
        finally:
            ACTIVE_PUBLIC_URL.reset(token)


class RequestSizeLimit:
    """Bound buffered JSON, including chunked input, before FastAPI parses it."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        declared = headers.get(b"content-length")
        if declared is not None and (len(declared) > 10 or not declared.isdigit() or int(declared) > MAX_REQUEST_BYTES):
            response = await http_error_handler(Request(scope), GatewayError(413,
                "Request body exceeds the configured byte limit or has invalid length.", "request_too_large"))
            return await response(scope, receive, send)
        body = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            chunk = event.get("body", b"")
            if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                response = await http_error_handler(Request(scope), GatewayError(413,
                    "Request body exceeds the configured byte limit.", "request_too_large"))
                return await response(scope, receive, send)
            body.extend(chunk)
            if not event.get("more_body", False):
                break
        replayed = False
        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        await self.app(scope, replay, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 65)
    logger.info("Starting Virel AI — Google AI Studio Web Hook Gateway")
    logger.info(f"Default Model: {DEFAULT_MODEL} | Thinking: {THINKING_MODE}")
    logger.info(f"Profile: {CHROME_PROFILE_DIR} | Headless: {HEADLESS}")
    logger.info(f"Port: {PORT} | Max Concurrent: {MAX_CONCURRENT} | Rate Limit: {RATE_LIMIT}")
    from .runtime import account_manager
    active_acc = account_manager.get_active_account()
    logger.info(f"Accounts: {len(account_manager.accounts)} configured | Active: {active_acc.id} ({active_acc.label})")
    logger.info("=" * 65)
    _get_semaphore()
    await asyncio.to_thread(prune_files)
    auto_start = os.getenv("VIREL_AUTO_START_BROWSER", "true").lower() in ("true", "1", "yes")
    if auto_start:
        startup_task = asyncio.create_task(browser_manager.start())
    else:
        logger.info("Browser engine auto-start is disabled (VIREL_AUTO_START_BROWSER=false). Start the engine from /dashboard when ready.")
    cleanup = asyncio.create_task(expiry_loop())
    pool_cleanup = asyncio.create_task(browser_manager.maintenance())
    try:
        yield
    finally:
        cleanup.cancel()
        pool_cleanup.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup
        with suppress(asyncio.CancelledError):
            await pool_cleanup
        await browser_manager.stop()
    logger.info("Virel AI Gateway stopped.")


app = FastAPI(
    title="Virel AI — Google AI Studio Web Hook Gateway",
    description="Browser-backed HTTP gateway for AI Studio; client compatibility under development",
    version="0.1.1",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(HTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(JSONDecodeError, validation_error_handler)
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestSizeLimit)
app.add_middleware(BrowserRequestMiddleware, pool=browser_manager)
app.add_middleware(PublicUrlAllowlistMiddleware)

for route_module in (chat, responses, completions, system, files, audio, image_generation, anthropic, mcp, dashboard_api):
    app.include_router(route_module.router)
app.include_router(anthropic.desktop_router)
