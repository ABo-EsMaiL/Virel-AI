"""Current Responses compatibility adapter; not full native Responses."""

import json
import logging
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from ..auth import verify_api_key
from ..errors import GatewayError, provider_error
from ..generation import checked_stream, require_ready, validate_options, usage_headers
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
    if not isinstance(body, dict):
        raise GatewayError(400, "Expected a JSON object.", "invalid_request")
    validate_options(body)
    if body.get("prompt"):
        raise GatewayError(400, "Reusable prompt templates are not supported yet.", "unsupported_capability")
    require_ready()
    for item in body.get("input", []) if isinstance(body.get("input"), list) else []:
        if isinstance(item, dict):
            if item.get("type", "message") != "message":
                raise GatewayError(400, "Only text message input is supported.", "unsupported_capability")
            content = item.get("content", [])
            if not isinstance(content, (str, list)):
                raise GatewayError(400, "Message content must be text.", "invalid_request")
            if isinstance(content, list) and any(isinstance(part, dict) and not isinstance(part.get("text"), str) for part in content):
                raise GatewayError(400, "Text parts require a string text value.", "invalid_request")
            if isinstance(content, list) and any(not isinstance(part, dict) or part.get("type") not in ("input_text", "output_text", "text") for part in content):
                raise GatewayError(400, "This Responses stage accepts text content only.", "unsupported_capability")
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
            prompt = last_msg
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
        raw_messages = body["messages"]
        if not isinstance(raw_messages, list) or any(
            not isinstance(message, dict) or not isinstance(message.get("role"), str)
            or not isinstance(message.get("content"), str) for message in raw_messages
        ):
            raise GatewayError(400, "Messages require a role and text content.", "invalid_request")
        messages = [ChatMessage(**message) for message in raw_messages]
        prompt = format_messages_to_prompt(messages)

    if not prompt.strip():
        raise GatewayError(400, "A nonempty text prompt is required.", "empty_prompt")

    if instructions and not prompt.startswith("[System"):
        prompt = f"[System Instructions]\n{instructions}\n\n{prompt}"

    batch_size_header = request.headers.get("x-batch-size")
    batch_size = int(batch_size_header) if (batch_size_header and batch_size_header.isdigit()) else None
    logger.info("Incoming /v1/responses chars=%s batch_size=%s", len(prompt), batch_size)

    now = int(time.time())
    resp_id = f"resp_{uuid.uuid4().hex[:16]}"

    if stream:
        async def sse_response_generator():
            try:
                async with sem:
                    async with browser_manager.lock:
                        async for chunk_data in checked_stream(prompt, resp_id, model_name=model_name, batch_size=batch_size):
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
                                    "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": delta, "annotations": []}]}]
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
            except GatewayError as exc:
                yield f"data: {json.dumps({'error': provider_error(exc)})}\n\n"

        return StreamingResponse(
            sse_response_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    else:
        full_text = ""
        async with sem:
            async with browser_manager.lock:
                async for chunk_data in checked_stream(prompt, resp_id, model_name=model_name, batch_size=batch_size):
                    if isinstance(chunk_data, dict):
                        full_text = chunk_data["text"]
                    else:
                        full_text += chunk_data

        response_payload = {
            "id": resp_id,
            "object": "response",
            "created_at": now,
            "status": "completed",
            "store": False,
            "model": model_name,
            "output": [
                {
                    "type": "message",
                    "id": f"msg_{uuid.uuid4().hex[:16]}",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "annotations": [],
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
            "usage": browser_manager.last_usage.responses() if browser_manager.last_usage else None
        }
        timings = getattr(browser_manager, "last_timings", {})
        headers = {
            "X-Timing-PreExec": f"{timings.get('pre_exec', 0.0):.2f}s",
            "X-Timing-Generation": f"{timings.get('generation', 0.0):.2f}s",
            "X-Timing-Total": f"{timings.get('total', 0.0):.2f}s"
        }
        headers.update(usage_headers(resp_id))
        return JSONResponse(response_payload, headers=headers)
