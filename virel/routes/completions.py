"""Legacy text completions adapter."""

import time
import uuid
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from ..auth import verify_api_key
from ..config import DEFAULT_MODEL, RATE_LIMIT
from ..runtime import browser_manager, limiter, _get_semaphore

router = APIRouter()


@router.post("/v1/completions", dependencies=[Depends(verify_api_key)])
@limiter.limit(RATE_LIMIT)
async def legacy_completions(request: Request):
    """Legacy OpenAI /v1/completions endpoint."""
    body = await request.json()
    prompt = body.get("prompt", "")
    if isinstance(prompt, list):
        prompt = " ".join([str(p) for p in prompt])
    model_name = body.get("model", DEFAULT_MODEL)
    batch_size_header = request.headers.get("x-batch-size")
    batch_size = int(batch_size_header) if (batch_size_header and batch_size_header.isdigit()) else None
    now = int(time.time())
    chunk_id = f"cmpl-{uuid.uuid4().hex[:12]}"

    full_text = ""
    sem = _get_semaphore()
    async with sem:
        async with browser_manager.lock:
            async for chunk_data in browser_manager.send_prompt_and_stream(str(prompt), batch_size=batch_size):
                if isinstance(chunk_data, dict):
                    full_text = chunk_data["text"]
                else:
                    full_text += chunk_data

    return JSONResponse({
        "id": chunk_id,
        "object": "text_completion",
        "created": now,
        "model": model_name,
        "choices": [{
            "text": full_text,
            "index": 0,
            "logprobs": None,
            "finish_reason": "stop"
        }]
    })
