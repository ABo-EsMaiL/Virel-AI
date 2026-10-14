"""FastAPI composition and startup/shutdown; no request transformations here."""

import logging
from json import JSONDecodeError
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .images import MAX_REQUEST_BYTES
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from .errors import http_error_handler, validation_error_handler, rate_limit_handler
from slowapi.errors import RateLimitExceeded

from .config import DEFAULT_MODEL, THINKING_MODE, CHROME_PROFILE_DIR, HEADLESS, PORT, MAX_CONCURRENT, RATE_LIMIT
from .runtime import browser_manager, limiter, _get_semaphore
from .routes import chat, responses, completions, system

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("virel.webhook")


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
            response = JSONResponse({"error": {"message": "Request body exceeds the 32 MiB limit or has invalid length.",
                "type": "invalid_request_error", "code": "request_too_large"}}, status_code=413)
            return await response(scope, receive, send)
        body = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            chunk = event.get("body", b"")
            if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                response = JSONResponse({"error": {"message": "Request body exceeds the 32 MiB limit.",
                    "type": "invalid_request_error", "code": "request_too_large"}}, status_code=413)
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
    logger.info("=" * 65)
    _get_semaphore()
    await browser_manager.start()
    yield
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

for route_module in (chat, responses, completions, system):
    app.include_router(route_module.router)
