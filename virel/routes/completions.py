"""Legacy text completions adapter."""

import time
import uuid
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from ..auth import verify_api_key
from ..errors import GatewayError
from ..generation import checked_stream, require_ready, validate_options, usage_headers, response_model, reasoning_headers
from ..config import DEFAULT_MODEL, RATE_LIMIT
from ..runtime import browser_manager, limiter, _get_semaphore

router = APIRouter()


@router.post("/v1/completions", dependencies=[Depends(verify_api_key)])
@limiter.limit(RATE_LIMIT)
async def legacy_completions(request: Request):
    """Legacy OpenAI /v1/completions endpoint."""
    body = await request.json()
    generation_options = validate_options(body)
    await require_ready()
    prompt = body.get("prompt", "")
    if isinstance(prompt, list):
        prompt = " ".join([str(p) for p in prompt])
    if not isinstance(prompt, str) or not prompt.strip():
        raise GatewayError(400, "A nonempty text prompt is required.", "empty_prompt")
    model_name = body.get("model", DEFAULT_MODEL)
    batch_size_header = request.headers.get("x-batch-size")
    batch_size = int(batch_size_header) if (batch_size_header and batch_size_header.isdigit()) else None
    now = int(time.time())
    chunk_id = f"cmpl-{uuid.uuid4().hex[:12]}"

    full_text = ""
    sem = _get_semaphore()
    async with sem:
        async with browser_manager.lock:
            async for chunk_data in checked_stream(str(prompt), chunk_id, model_name=model_name, batch_size=batch_size, **generation_options):
                if isinstance(chunk_data, dict):
                    full_text = chunk_data["text"]
                else:
                    full_text += chunk_data

            return JSONResponse({
                "id": chunk_id,
                "object": "text_completion",
                "usage": browser_manager.last_usage.chat() if browser_manager.last_usage else None,
                "created": now,
                "model": response_model(model_name),
                "requested_model": model_name,
                "choices": [{
                    "text": full_text,
                    "index": 0,
                    "logprobs": None,
                    "finish_reason": "length" if browser_manager.last_finish_reason == "max_tokens" else "stop"
                }]
            }, headers={**usage_headers(chunk_id), **reasoning_headers(body)})
