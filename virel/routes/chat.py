"""Chat Completions JSON/SSE and vision adapter."""

import logging
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from ..tools import is_tool_request, function_response
from ..streaming import stream_response, text_events, validate_stream
from ..auth import verify_api_key
from ..errors import GatewayError
from ..generation import checked_stream, require_ready, validate_options, usage_headers, response_model
from ..config import DEFAULT_MODEL, RATE_LIMIT
from ..runtime import browser_manager, limiter, _get_semaphore
from ..schemas import ChatRequest
from ..messages import extract_prompt_and_images

logger = logging.getLogger("virel.webhook")
router = APIRouter()


@router.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
@limiter.limit(RATE_LIMIT)
async def chat_completions(request: Request, chat_request: ChatRequest):
    """OpenAI-compatible chat completions endpoint driven by Google AI Studio Web."""
    sem = _get_semaphore()
    if sem.locked():
        raise HTTPException(
            status_code=429,
            detail={"error": "Server busy — browser tab currently processing another request.", "type": "concurrency_limit"}
        )

    body = await request.json()
    include_usage = validate_stream(body)
    if is_tool_request(body):
        return await function_response(body, False, sem, owner=request.headers.get("authorization", ""))
    generation_options = validate_options(body)
    await require_ready()
    prompt, images = extract_prompt_and_images(chat_request.messages)
    if not prompt.strip() and not images:
        raise GatewayError(400, "A nonempty text prompt is required.", "empty_prompt")
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    now = int(time.time())
    model_name = chat_request.model or DEFAULT_MODEL
    batch_size_header = request.headers.get("x-batch-size")
    batch_size = int(batch_size_header) if (batch_size_header and batch_size_header.isdigit()) else None

    # Check search toggle header
    search_hdr = request.headers.get("x-google-search-enabled") or request.headers.get("x-enable-search")
    enable_search = None
    if search_hdr is not None:
        enable_search = search_hdr.lower() in ("true", "1", "yes")

    logger.info(
        f"Incoming /v1/chat/completions prompt ({len(prompt)} chars, images={len(images)}, batch_size={batch_size}, "
        f"google_search={'INHERITED' if enable_search is None else ('ENABLED' if enable_search else 'DISABLED')})"
    )

    if chat_request.stream:
        return stream_response(text_events(prompt, chunk_id, now, model_name, False, sem,
            batch_size=batch_size, enable_search=enable_search, images=images, **generation_options),
            False, chunk_id, now, model_name, include_usage)
    else:
        full_text = ""
        async with sem:
            async with browser_manager.lock:
                async for chunk_data in checked_stream(prompt, chunk_id, model_name=model_name, batch_size=batch_size, enable_search=enable_search, images=images, **generation_options):
                    if isinstance(chunk_data, dict):
                        full_text = chunk_data["text"]
                    else:
                        full_text += chunk_data

                timings = getattr(browser_manager, "last_timings", {})
                headers = {
                    "X-Timing-PreExec": f"{timings.get('pre_exec', 0.0):.2f}s",
                    "X-Timing-Generation": f"{timings.get('generation', 0.0):.2f}s",
                    "X-Timing-Total": f"{timings.get('total', 0.0):.2f}s",
                    "X-Batch-Size": str(batch_size or 0),
                    "X-Google-Search-Enabled": str(browser_manager.google_search_enabled).lower(),
                    "X-Tool-Calls-Count": str(browser_manager.last_tool_calls_count),
                    "X-Thinking-Mode": str(browser_manager.active_thinking),
                    "X-Final-Status": str(timings.get('state', 'UNKNOWN')),
                }
                headers.update(usage_headers(chunk_id))
                return JSONResponse({
                    "id": chunk_id,
                    "object": "chat.completion",
                    "created": now,
                    "model": response_model(model_name),
                    "requested_model": model_name,
                    "usage": browser_manager.last_usage.chat() if browser_manager.last_usage else None,
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": full_text
                        },
                        "finish_reason": "stop"
                    }]
                }, headers=headers)
