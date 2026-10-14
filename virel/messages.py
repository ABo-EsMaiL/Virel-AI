"""Faithful caller history and supported media source normalization."""

import json
from typing import Any, List, Tuple

from .errors import GatewayError
from .schemas import ChatMessage


def extract_prompt_and_images(messages: List[ChatMessage]) -> Tuple[str, List[Any]]:
    turns, sources = [], []
    has_text = False
    for message in messages:
        if message.role not in ("system", "developer", "user", "assistant"):
            raise GatewayError(400, "Unsupported message role.", "unsupported_role")
        content = "" if message.content is None else message.content
        text_parts = []
        if isinstance(content, str):
            text_parts.append(content)
            has_text |= bool(content.strip())
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    raise GatewayError(400, "Message parts must be objects.", "invalid_request")
                if part.get("type") == "text":
                    if not isinstance(part.get("text"), str):
                        raise GatewayError(400, "Text parts require a string text value.", "invalid_request")
                    text_parts.append(part["text"])
                    has_text |= bool(part["text"].strip())
                elif part.get("type") == "image_url":
                    info = part.get("image_url")
                    if message.role != "user":
                        raise GatewayError(400, "This stage accepts images only in user messages.", "unsupported_capability")
                    if not isinstance(info, dict) or not isinstance(info.get("url"), str) or not info["url"]:
                        raise GatewayError(400, "Images require a URL or data image.", "invalid_image")
                    if info.get("detail", "auto") != "auto":
                        raise GatewayError(400, "Only default image detail is supported.", "unsupported_parameter")
                    sources.append(info["url"])
                    text_parts.append(f"[Attached image {len(sources)}]")
                elif part.get("type") == "file":
                    info = part.get("file")
                    if message.role != "user":
                        raise GatewayError(400, "PDFs are accepted only in user messages.", "unsupported_capability")
                    if not isinstance(info, dict):
                        raise GatewayError(400, "A PDF file source is required.", "invalid_file")
                    sources.append(info)
                    text_parts.append(f"[Attached PDF {sum(isinstance(source, dict) for source in sources)}]")
                else:
                    raise GatewayError(400, "Unsupported message content type.", "unsupported_capability")
        else:
            raise GatewayError(400, "Message content must be text or supported parts.", "invalid_request")
        turns.append({"role": message.role, "content": "\n".join(text_parts)})
    if sources and not has_text:
        prompt = "Describe the attached document." if any(isinstance(source, dict) for source in sources) else "Describe the attached image."
    elif not turns or not any(turn["content"].strip() for turn in turns):
        prompt = ""
    elif len(turns) == 1 and turns[0]["role"] == "user":
        prompt = turns[0]["content"]
    elif len(turns) == 2 and [turn["role"] for turn in turns] == ["system", "user"]:
        prompt = "[System Instructions]\n" + turns[0]["content"] + "\n\n" + turns[1]["content"]
    else:
        # shortcut: roles are text labels; use native UI turn controls when role enforcement is required.
        prompt = "Continue this conversation and answer the final message:\n" + json.dumps(turns, ensure_ascii=False)
    return prompt, sources


def format_messages_to_prompt(messages: List[ChatMessage]) -> str:
    prompt, _ = extract_prompt_and_images(messages)
    return prompt


def responses_messages(body):
    """Normalize supported Responses input, preserving roles and order."""
    raw = body.get("input", "")
    legacy = not raw and "messages" in body
    if legacy:
        raw = body["messages"]
    if isinstance(raw, str):
        result = [ChatMessage(role="user", content=raw)]
    elif isinstance(raw, list):
        result = []
        for item in raw:
            if isinstance(item, str) and not legacy:
                result.append(ChatMessage(role="user", content=item))
                continue
            if not isinstance(item, dict) or item.get("type", "message") != "message":
                raise GatewayError(400, "Only text message input is supported.", "unsupported_capability")
            role = item.get("role", None if legacy else "user")
            if not isinstance(role, str):
                raise GatewayError(400, "Messages require a text role.", "invalid_request")
            content = item.get("content", "")
            if isinstance(content, list) and not legacy:
                normalized = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "input_file":
                        normalized.append({"type": "file", "file": {key: value for key, value in part.items() if key != "type"}})
                        continue
                    if isinstance(part, dict) and part.get("type") == "input_image":
                        if part.get("file_id"):
                            raise GatewayError(400, "Stored image file IDs are not supported.", "unsupported_capability")
                        normalized.append({"type": "image_url", "image_url": {
                            "url": part.get("image_url"), "detail": part.get("detail", "auto")}})
                        continue
                    if not isinstance(part, dict) or part.get("type") not in ("input_text", "output_text", "text"):
                        raise GatewayError(400, "Unsupported Responses content type.", "unsupported_capability")
                    if not isinstance(part.get("text"), str):
                        raise GatewayError(400, "Text parts require a string text value.", "invalid_request")
                    normalized.append({"type": "text", "text": part["text"]})
                content = normalized
            elif not isinstance(content, str):
                raise GatewayError(400, "Messages require text content.", "invalid_request")
            result.append(ChatMessage(role=role, content=content))
    else:
        raise GatewayError(400, "Input must be text or messages.", "invalid_request")
    if body.get("instructions"):
        result.insert(0, ChatMessage(role="system", content=body["instructions"]))
    return result
