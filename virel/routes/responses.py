"""Current Responses compatibility adapter; not full native Responses."""

import json
import logging
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from ..auth import verify_api_key
from ..config import DEFAULT_MODEL, RATE_LIMIT
from ..runtime import browser_manager, limiter, _get_semaphore
from ..config import CLEAR_CHAT_ON_REQUEST
from ..schemas import ChatMessage
from ..messages import format_messages_to_prompt

logger = logging.getLogger("virel.webhook")
router = APIRouter()


@router.post("/v1/responses", dependencies=[Depends(verify_api_key)])
@router.post("/responses", dependencies=[Depends(verify_api_key)])
@limiter.limit(RATE_LIMIT)
async def responses_endpoint(request: Request):
    """
    OpenAI Responses API endpoint (used by newer n8n 'Message a Model' nodes).
    Handles 'input', 'messages', 'instructions' payloads.
    """
    sem = _get_semaphore()
    if sem.locked():
        raise HTTPException(
            status_code=429,
            detail={"error": "Server busy — browser tab currently processing another request.", "type": "concurrency_limit"}
        )

    body = await request.json()
    model_name = body.get("model", DEFAULT_MODEL)
    instructions = body.get("instructions", "")
    stream = body.get("stream", False)

    # Extract prompt from input or messages
    prompt = ""
    raw_input = body.get("input", "")
    if isinstance(raw_input, str):
        prompt = raw_input
    elif isinstance(raw_input, list):
        if not CLEAR_CHAT_ON_REQUEST:
            # Continuous chat: only extract the latest user message
            last_msg = ""
            for item in reversed(raw_input):
                if isinstance(item, str):
                    last_msg = item.strip()
                    break
                elif isinstance(item, dict):
                    if item.get("role", "user") == "user":
                        content = item.get("content", "")
                        if isinstance(content, list):
                            content = " ".join([c.get("text", "") for c in content if isinstance(c, dict) and "text" in c])
                        last_msg = str(content).strip()
                        break
            prompt = last_msg or "Hello"
        else:
            parts = []
            for item in raw_input:
                if isinstance(item, str):
                    parts.append(item.strip())
                elif isinstance(item, dict):
                    content = item.get("content", "")
                    if isinstance(content, list):
                        content = " ".join([c.get("text", "") for c in content if isinstance(c, dict) and "text" in c])
                    role = item.get("role", "user")
                    if len(raw_input) == 1 and role == "user":
                        parts.append(str(content).strip())
                    else:
                        parts.append(f"{role}: {content}")
            prompt = "\n".join(parts)

    if not prompt and "messages" in body:
        messages = [ChatMessage(**m) for m in body["messages"]]
        prompt = format_messages_to_prompt(messages)

    if instructions and not prompt.startswith("[System"):
        prompt = f"[System Instructions]\n{instructions}\n\n{prompt}"

    if not prompt:
        prompt = "Hello"

    batch_size_header = request.headers.get("x-batch-size")
    batch_size = int(batch_size_header) if (batch_size_header and batch_size_header.isdigit()) else None
    logger.info(f"Incoming /v1/responses prompt ({len(prompt)} chars, batch_size={batch_size}): {repr(prompt[:80])}")

    now = int(time.time())
    resp_id = f"resp_{uuid.uuid4().hex[:16]}"

    if stream:
        async def sse_response_generator():
            async with sem:
                async with browser_manager.lock:
                    async for chunk_data in browser_manager.send_prompt_and_stream(prompt, model_name=model_name, batch_size=batch_size):
                        if isinstance(chunk_data, dict):
                            delta = chunk_data["delta"]
                        else:
                            delta = chunk_data
                            
                        if delta:
                            chunk = {
                                "id": resp_id,
                                "object": "response.chunk",
                                "created_at": now,
                                "model": model_name,
                                "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                                "output": [{"type": "message", "role": "assistant", "content": [{"type": "text", "text": delta}]}]
                            }
                            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                    done_chunk = {
                        "id": resp_id,
                        "object": "response.done",
                        "created_at": now,
                        "model": model_name,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                    }
                    yield f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"

        return StreamingResponse(
            sse_response_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    else:
        full_text = ""
        async with sem:
            async with browser_manager.lock:
                async for chunk_data in browser_manager.send_prompt_and_stream(prompt, model_name=model_name, batch_size=batch_size):
                    if isinstance(chunk_data, dict):
                        full_text = chunk_data["text"]
                    else:
                        full_text += chunk_data

        response_payload = {
            "id": resp_id,
            "object": "response",
            "created_at": now,
            "status": "completed",
            "model": model_name,
            "output": [
                {
                    "type": "message",
                    "id": f"msg_{uuid.uuid4().hex[:16]}",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "text",
                            "text": full_text
                        }
                    ]
                }
            ],
            "output_text": full_text,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": full_text
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "total_tokens": len(full_text.split()) + len(prompt.split()),
                "input_tokens": len(prompt.split()),
                "output_tokens": len(full_text.split())
            }
        }
        timings = getattr(browser_manager, "last_timings", {})
        headers = {
            "X-Timing-PreExec": f"{timings.get('pre_exec', 0.0):.2f}s",
            "X-Timing-Generation": f"{timings.get('generation', 0.0):.2f}s",
            "X-Timing-Total": f"{timings.get('total', 0.0):.2f}s"
        }
        return JSONResponse(response_payload, headers=headers)
