"""SSE wire protocols over observed text and fully validated client tool batches."""
import asyncio
from contextlib import aclosing
import json
import uuid
from fastapi.responses import StreamingResponse
from .errors import GatewayError, provider_error
from .generation import checked_stream, response_model
from .runtime import browser_manager


def validate_stream(body, responses=False):
    stream = body.get("stream", False)
    if not isinstance(stream, bool):
        raise GatewayError(400, "stream must be boolean.", "invalid_request")
    options = body.get("stream_options")
    if options is None:
        return False
    if responses or not stream or not isinstance(options, dict) or set(options) - {"include_usage"}:
        raise GatewayError(400, "stream_options is available only for streamed Chat include_usage.", "invalid_request")
    if "include_usage" in options and not isinstance(options["include_usage"], bool):
        raise GatewayError(400, "include_usage must be boolean.", "invalid_request")
    return options.get("include_usage", False)


def read_text(item, previous):
    if isinstance(item, dict) and "text" in item:
        current = item["text"]
    else:
        delta = item.get("delta", "") if isinstance(item, dict) else item
        current = previous + delta if isinstance(delta, str) else None
    if not isinstance(current, str) or not current.startswith(previous):
        raise GatewayError(502, "AI Studio rewrote text already delivered by the stream.", "upstream_text_rewritten")
    return current, current[len(previous):]


def text_payload(responses, identifier, now, model, text):
    usage = browser_manager.last_usage
    message = {"role": "assistant", "content": text}
    common = {"id": identifier, "model": response_model(model), "requested_model": model}
    if not responses:
        return {**common, "object": "chat.completion", "created": now,
                "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                "usage": usage.chat() if usage else None}
    return {**common, "object": "response", "created_at": now, "status": "completed", "store": False,
            "error": None, "incomplete_details": None,
            "output": [{"type": "message", "id": "msg_" + uuid.uuid4().hex[:16], "role": "assistant", "status": "completed", "phase": "final_answer",
                        "content": [{"type": "output_text", "text": text, "annotations": []}]}],
            "output_text": text, "usage": usage.responses() if usage else None}


async def text_events(prompt, identifier, now, model, responses, sem, **options):
    text = ""
    async with sem:
        async with browser_manager.lock:
            async with aclosing(checked_stream(prompt, identifier, model_name=model, **options)) as source:
                async for item in source:
                    text, delta = read_text(item, text)
                    if delta:
                        yield {"delta": delta, "model": response_model(model)}
            yield {"response": text_payload(responses, identifier, now, model, text)}


def stream_response(source, responses, identifier, now, model, include_usage=False, headers=None):
    async def serialize():
        final = None
        pending = None
        started = False
        message_started = False
        message_id = "msg_" + uuid.uuid4().hex[:16]
        text = ""
        actual = model
        sequence = 0
        def event(kind, **values):
            nonlocal sequence
            payload = {"type": kind, "sequence_number": sequence, **values}
            sequence += 1
            return "event: " + kind + "\ndata: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
        def response(status, **values):
            return {"id": identifier, "object": "response", "created_at": now, "model": actual, "requested_model": model,
                    "status": status, "store": False, "output": [], "usage": None, "error": None, "incomplete_details": None, **values}
        def message(status, content):
            return {"id": message_id, "type": "message", "role": "assistant", "status": status, "content": content}
        def part(value):
            return {"type": "output_text", "text": value, "annotations": []}
        def chat(delta=None, finish=None, usage_only=False, usage=None):
            payload = {"id": identifier, "object": "chat.completion.chunk", "created": now, "model": actual,
                       "requested_model": model, "choices": [] if usage_only else [{"index": 0, "delta": delta or {}, "finish_reason": finish}]}
            if include_usage:
                payload["usage"] = usage
            return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
        try:
            async with aclosing(source):
                async for item in source:
                    final = item.get("response", final)
                    pending = item.get("pending", pending)
                    actual = final["model"] if final else item.get("model", actual)
                    if not started:
                        if responses:
                            yield event("response.created", response=response("in_progress"))
                            yield event("response.in_progress", response=response("in_progress"))
                        else:
                            yield chat({"role": "assistant", "content": ""})
                        started = True
                    delta = item.get("delta", "")
                    if delta:
                        if responses and not message_started:
                            yield event("response.output_item.added", output_index=0, item=message("in_progress", []))
                            yield event("response.content_part.added", item_id=message_id, output_index=0, content_index=0, part=part(""))
                        message_started = True
                        text += delta
                        # Bound the typing effect to 60 steps even for very long replies.
                        step = max(16, (len(delta) + 59) // 60)
                        for offset in range(0, len(delta), step):
                            if offset:
                                await asyncio.sleep(0.025)
                            fragment = delta[offset:offset + step]
                            if responses:
                                yield event("response.output_text.delta", item_id=message_id, output_index=0, content_index=0, delta=fragment, logprobs=[])
                            else:
                                yield chat({"content": fragment})
            if final is None:
                raise GatewayError(502, "The stream ended without a completed result.", "incomplete_upstream_stream")
            if responses:
                for index, output in enumerate(final["output"]):
                    if output["type"] == "message":
                        output["id"] = message_id
                        if not message_started:
                            yield event("response.output_item.added", output_index=index, item=message("in_progress", []))
                            yield event("response.content_part.added", item_id=message_id, output_index=index, content_index=0, part=part(""))
                        yield event("response.output_text.done", item_id=message_id, output_index=index, content_index=0, text=output["content"][0]["text"], logprobs=[])
                        yield event("response.content_part.done", item_id=message_id, output_index=index, content_index=0, part=output["content"][0])
                    elif output["type"] == "function_call":
                        yield event("response.output_item.added", output_index=index, item={**output, "status": "in_progress", "arguments": ""})
                        yield event("response.function_call_arguments.delta", item_id=output["id"], output_index=index, delta=output["arguments"])
                        yield event("response.function_call_arguments.done", item_id=output["id"], output_index=index, arguments=output["arguments"])
                    yield event("response.output_item.done", output_index=index, item=output)
                yield event("response.completed", response=final)
            else:
                choice = final["choices"][0]
                for index, call in enumerate(choice["message"].get("tool_calls", [])):
                    yield chat({"tool_calls": [{"index": index, **call}]})
                yield chat(finish=choice["finish_reason"])
                if include_usage:
                    yield chat(usage_only=True, usage=final.get("usage"))
                yield "data: [DONE]\n\n"
        except GatewayError as error:
            if responses:
                failure = provider_error(error)
                yield event("response.failed", response=response("failed", error={"code": failure["code"], "message": failure["message"]},
                    output=[message("incomplete", [part(text)])] if message_started else []))
            else:
                yield "data: " + json.dumps({"error": provider_error(error)}) + "\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            if pending is not None and browser_manager.tool_run.pending is pending:
                browser_manager.tool_run.clear()
            raise
    return StreamingResponse(serialize(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-Request-ID": identifier,
        "X-Virel-Usage-Delivery": "final_event", "X-Virel-Text-Delivery": "completed_browser_snapshot_paced", **(headers or {})})
