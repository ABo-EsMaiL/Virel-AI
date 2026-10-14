"""Chat Completions JSON/SSE and vision adapter."""

import json
import logging
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from ..auth import verify_api_key
from ..config import DEFAULT_MODEL, RATE_LIMIT, ENABLE_SEARCH_GROUNDING
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

    prompt, images = extract_prompt_and_images(chat_request.messages)
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
    else:
        enable_search = ENABLE_SEARCH_GROUNDING

    logger.info(
        f"Incoming /v1/chat/completions prompt ({len(prompt)} chars, images={len(images)}, batch_size={batch_size}, "
        f"google_search={'ENABLED' if enable_search else 'DISABLED'}): {repr(prompt[:80])}"
    )

    async def sse_generator():
        async with sem:
            async with browser_manager.lock:
                first_chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": now,
                    "model": model_name,
                    "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]
                }
                yield f"data: {json.dumps(first_chunk, ensure_ascii=False)}\n\n"

                async for chunk_data in browser_manager.send_prompt_and_stream(prompt, model_name=model_name, batch_size=batch_size, enable_search=enable_search, images=images):
                    if isinstance(chunk_data, dict):
                        delta = chunk_data["delta"]
                    else:
                        delta = chunk_data
                        
                    if delta:
                        chunk = {
                            "id": chunk_id,
                            "object": "chat.completion.chunk",
                            "created": now,
                            "model": model_name,
                            "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}]
                        }
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

                done_chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": now,
                    "model": model_name,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                }
                yield f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

    if chat_request.stream:
        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        full_text = ""
        async with sem:
            async with browser_manager.lock:
                async for chunk_data in browser_manager.send_prompt_and_stream(prompt, model_name=model_name, batch_size=batch_size, enable_search=enable_search, images=images):
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
        return JSONResponse({
            "id": chunk_id,
            "object": "chat.completion",
            "created": now,
            "model": model_name,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": full_text
                },
                "finish_reason": "stop"
            }]
        }, headers=headers)
