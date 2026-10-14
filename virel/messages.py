"""Faithful caller history and existing incoming image preparation."""

import base64
import json
import logging
import os
import uuid
from typing import List, Tuple

from .config import TEMP_UPLOADS_DIR
from .errors import GatewayError
from .schemas import ChatMessage

logger = logging.getLogger("virel.webhook")


def extract_prompt_and_images(messages: List[ChatMessage]) -> Tuple[str, List[str]]:
    turns = []
    image_paths = []
    for message in messages:
        if message.role not in ("system", "developer", "user", "assistant"):
            raise GatewayError(400, "This stage accepts system, developer, user and assistant text roles.", "unsupported_role")
        content = message.content
        text_parts = []
        if content is None:
            content = ""
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    raise GatewayError(400, "Message parts must be objects.", "invalid_request")
                p_type = part.get("type", "")
                if p_type == "text":
                    if not isinstance(part.get("text"), str):
                        raise GatewayError(400, "Text parts require a string text value.", "invalid_request")
                    text_parts.append(part["text"])
                elif p_type == "image_url":
                    img_info = part.get("image_url", {})
                    url = img_info.get("url", "") if isinstance(img_info, dict) else str(img_info)
                    url = url.strip()
                    if not url:
                        continue
                    if url.startswith("data:image/"):
                        try:
                            # format: data:image/webp;base64,...
                            header, b64_data = url.split(";base64,", 1)
                            ext = header.split("data:image/", 1)[1].split(";")[0].strip()
                            if not ext or ext == "*":
                                ext = "webp"
                            elif ext.lower() == "jpeg":
                                ext = "jpg"
                            filename = f"upload_{uuid.uuid4().hex[:12]}.{ext}"
                            file_path = os.path.join(TEMP_UPLOADS_DIR, filename)
                            with open(file_path, "wb") as f_img:
                                f_img.write(base64.b64decode(b64_data))
                            image_paths.append(file_path)
                            logger.info(f"Saved incoming Base64 image to: {file_path} ({os.path.getsize(file_path)} bytes)")
                        except Exception as e:
                            logger.error(f"Failed to decode base64 image: {e}")
                    elif os.path.exists(url):
                        image_paths.append(os.path.abspath(url))
                    elif url.startswith("http://") or url.startswith("https://"):
                        try:
                            import urllib.request
                            ext = os.path.splitext(url.split("?")[0])[1] or ".jpg"
                            filename = f"dl_{uuid.uuid4().hex[:12]}{ext}"
                            file_path = os.path.join(TEMP_UPLOADS_DIR, filename)
                            urllib.request.urlretrieve(url, file_path)
                            image_paths.append(file_path)
                            logger.info(f"Downloaded remote image to: {file_path}")
                        except Exception as e:
                            logger.error(f"Failed to download image URL {url}: {e}")

                else:
                    raise GatewayError(400, "This message content type is not supported yet.", "unsupported_capability")
        else:
            raise GatewayError(400, "Message content must be text or supported parts.", "invalid_request")
        turns.append({"role": message.role, "content": "\n".join(text_parts)})

    if not turns or not any(turn["content"].strip() for turn in turns):
        prompt = ""
    elif len(turns) == 1 and turns[0]["role"] == "user":
        prompt = turns[0]["content"]
    elif len(turns) == 2 and [turn["role"] for turn in turns] == ["system", "user"]:
        prompt = "[System Instructions]\n" + turns[0]["content"] + "\n\n" + turns[1]["content"]
    else:
        # shortcut: roles are text labels; use native UI turn controls when role enforcement is required.
        prompt = "Continue this conversation and answer the final message:\n" + json.dumps(turns, ensure_ascii=False)
    return prompt, image_paths


def format_messages_to_prompt(messages: List[ChatMessage]) -> str:
    prompt, _ = extract_prompt_and_images(messages)
    return prompt


def responses_messages(body):
    """Normalize only supported Responses text input, preserving roles and order."""
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
                    if not isinstance(part, dict) or part.get("type") not in ("input_text", "output_text", "text"):
                        raise GatewayError(400, "This Responses stage accepts text content only.", "unsupported_capability")
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
