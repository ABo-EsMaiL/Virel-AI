"""FastAPI composition and startup/shutdown; no request transformations here."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import DEFAULT_MODEL, THINKING_MODE, CHROME_PROFILE_DIR, HEADLESS, PORT, MAX_CONCURRENT, RATE_LIMIT
from .runtime import browser_manager, limiter, _get_semaphore
from .routes import chat, responses, completions, system

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("virel.webhook")


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
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


for route_module in (chat, responses, completions, system):
    app.include_router(route_module.router)
