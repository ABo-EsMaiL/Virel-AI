"""Message-to-prompt conversion and incoming image file preparation."""

import base64
import logging
import os
import re
import uuid
from typing import List, Tuple

from .config import TEMP_UPLOADS_DIR
from .schemas import ChatMessage

logger = logging.getLogger("virel.webhook")


def extract_prompt_and_images(messages: List[ChatMessage]) -> Tuple[str, List[str]]:
    """
    Combines user/system messages into a pristine prompt string and extracts any image URLs
    (supporting Base64 data URLs, remote URLs, and local file paths).
    """
    system_lines = []
    user_lines = []
    image_paths = []

    for m in messages:
        content = m.content or ""
        if isinstance(content, str):
            text_val = content.strip()
            if text_val:
                if m.role == "system":
                    system_lines.append(text_val)
                elif m.role == "user":
                    user_lines.append(text_val)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                p_type = part.get("type", "")
                if p_type == "text":
                    t = str(part.get("text", "")).strip()
                    if t:
                        if m.role == "system":
                            system_lines.append(t)
                        elif m.role == "user":
                            user_lines.append(t)
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

    # Sanitize user content: remove any leaked thoughts or historical reasoning markers
    clean_user_lines = []
    for u in user_lines:
        u_clean = re.sub(r'<\s*thought\b[^>]*>.*?<\s*/\s*thought\s*>', '', u, flags=re.DOTALL | re.IGNORECASE)
        u_clean = re.sub(r'\*\*(?:Defining the Problem|Refining the Matching Criteria|Analyzing Match Results|Thinking Process)\*\*.*?(?=\n\n|$)', '', u_clean, flags=re.DOTALL)
        u_clean = re.sub(r'(?:Defining the Problem|Refining the Matching Criteria|Analyzing Match Results|I\'ve just\b).*?(?=\n\n|$)', '', u_clean, flags=re.DOTALL)
        u_clean = u_clean.strip()
        if u_clean:
            clean_user_lines.append(u_clean)

    parts = []
    if system_lines:
        parts.append("[System Instructions]\n" + "\n\n".join(system_lines))

    if clean_user_lines:
        parts.append("\n\n".join(clean_user_lines))

    prompt = "\n\n".join(parts)
    return prompt, image_paths


def format_messages_to_prompt(messages: List[ChatMessage]) -> str:
    """Combines user/system messages into a pristine, clean prompt string, completely omitting any historical reasoning."""
    prompt, _ = extract_prompt_and_images(messages)
    return prompt
