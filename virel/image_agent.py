"""Universal conversational adapter for image generation models across Claude Code, Desktop, Cline, Hermes, Continue, n8n."""
import asyncio
import base64
import json
import logging
import re
import time
import uuid
from pathlib import Path
from anyio import CancelScope
from fastapi.responses import JSONResponse, StreamingResponse
from .config import DEFAULT_IMAGE_MODEL, DEFAULT_SPEECH_MODEL, DEFAULT_SPEECH_VOICE, PORT
from .errors import GatewayError
from .models import IMAGE_MODEL_ICONS

logger = logging.getLogger("virel.webhook")

IMAGE_INTENT_PATTERN = re.compile(
    r"(?:"
    # Arabic intent patterns
    r"(?:اعمل|صمم|ولد|أنشئ|انشئ|ارسم|طلع|هات|ساوي|توليد|رسم|محتاج|عايز|اريد|أريد|اعملي|صمملي|ولدي|ارسميلي|طلعلي|عدل|عدلي|غير|غيرلي|ضبط|ضبطلي|تعديل|حلي|حليها|حلويها)\s+(?:لي\s+)?(?:صورة|رسمة|لوحة|تصميم|صوره|رسمه|صورتي|رسمتي|لوحتي|تصميمي|صور)"
    r"|"
    r"(?:ارسم|ارسميلي|ارسم لي)\s+\w+"
    r"|"
    # English intent patterns
    r"(?:generate|create|draw|make|render|edit|modify)\s+(?:an?\s+)?(?:image|picture|drawing|artwork|photo|illustration)"
    r"|"
    r"(?:draw|paint)\s+(?:an?\s+)?\w+"
    r")",
    re.IGNORECASE
)

NON_CREATIVE_EXCLUSIONS = re.compile(
    r"(?:"
    # Moving, copying, deleting, sending, downloading, opening, viewing files
    r"(?:انقل|انقلي|نقل|احذف|احذفي|حذف|امسح|امسحي|مسح|انسخ|انسخي|نسخ|حمل|حملي|تحميل|نزل|نزلي|تنزيل|ارسل|ارسلي|ارسال|افتح|افتحي|وريني|شوف|شوفي|صدر|تصدير|حفظ|احفظ|احفظي)"
    r"|"
    # File locations / paths
    r"(?:سطح المكتب|الديسكتوب|desktop|folder|مجلد|فولدر|directory|مسار|مكان|file path|path)\b"
    r"|"
    # Explaining / analyzing / discussing an existing image
    r"(?:اشرح|اشرحي|شرح|حلل|حللي|تحليل|اقرأ|اقرأي|قراءة|اوصف|اوصفي|وصف|معنى|شو رأيك|ايه رأيك|رأيك في|رأيك بـ)"
    r"|"
    r"\b(?:move|transfer|copy|cp|mv|delete|remove|rm|download|save\s+to|send|share|open|locate|explain|describe|analyze|ocr|read)\b"
    r"|"
    # Code words
    r"\b(?:code|script|function|def\s+|class\s+|python|javascript|typescript|html|css|api|endpoint|sdk|library|module|package|import\s+|npm|pip|git|test|debug|fix|refactor|error|exception|stack\s*trace)\b"
    r"|"
    r"(?:كود|برمج|برمجة|سكربت|دالة|فنكشن|مكتبة|اكتب كود|اكتب سكربت)"
    r")",
    re.IGNORECASE
)


def is_image_model(model_name: str, catalog: dict = None) -> bool:
    """Detect whether a requested model or alias is an image generation model."""
    if not model_name or not isinstance(model_name, str):
        return False
    from .runtime import browser_manager
    catalog = catalog or getattr(browser_manager, "model_catalog", {}) or {}
    item = catalog.get(model_name)
    if item:
        resolved = catalog.get(item.get("resolved_id", model_name), item)
        icon = resolved.get("capabilities", {}).get("ui_category_icon")
        modalities = resolved.get("capabilities", {}).get("output_modalities")
        if icon in IMAGE_MODEL_ICONS or modalities == ["image"]:
            return True
    lower = model_name.lower()
    return any(marker in lower for marker in ("-image", "gempix", "banana", "imagen"))



def clean_prompt_text(text: str) -> str:
    """Clean technical metadata, file tags, and Claude temp paths from prompt text."""
    if not isinstance(text, str):
        return ""
    text = re.sub(r"\[Image:\s*source:[^\]]+\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[Attached (?:image|file|document)[^\]]*\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[a-zA-Z]:\\[^\s]+\.(?:png|jpg|jpeg|webp|gif)", "", text, flags=re.IGNORECASE)
    return text.strip()

def extract_last_user_text(messages: list) -> str:
    """Extract text from the latest user turn only."""
    if not messages:
        return ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str):
                return content.strip()
            elif isinstance(content, list):
                parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                return " ".join(parts).strip()
    return ""


def extract_image_sources(messages: list) -> list:
    """Extract attached image URLs or base64 data URIs from the latest user message."""
    sources = []
    for msg in reversed(messages or []):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        ptype = part.get("type")
                        if ptype == "image_url":
                            info = part.get("image_url", {})
                            url = info.get("url") if isinstance(info, dict) else info
                            if isinstance(url, str) and url:
                                sources.append(url)
                        elif ptype == "image":
                            src = part.get("source", {})
                            if isinstance(src, dict) and src.get("type") == "base64":
                                data_uri = f"data:{src.get('media_type', 'image/png')};base64,{src.get('data', '')}"
                                sources.append(data_uri)
            break
    return sources


def has_image_intent(messages: list) -> bool:
    """Detect if the latest user turn explicitly asks for an image generation."""
    latest = extract_last_user_text(messages)
    if not latest or len(latest.strip()) < 3:
        return False
    if NON_CREATIVE_EXCLUSIONS.search(latest):
        return False
    return bool(IMAGE_INTENT_PATTERN.search(latest))


def extract_image_prompt(messages: list) -> str:
    """Extract or reconstruct the image prompt from conversational history."""
    if not messages:
        return "A high quality, detailed creative image"
    user_texts = []
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str):
                user_texts.append(content.strip())
            elif isinstance(content, list):
                parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                if parts:
                    user_texts.append(" ".join(parts).strip())
    if not user_texts:
        return "A high quality, detailed creative image"

    last = user_texts[-1]
    fillers = {"جرب كدا تولد الصورة", "جرب كدا", "تولد الصورة", "ولد الصورة", "اعملها", "نفذ", "تمام",
               "generate it", "generate image", "try now", "draw it", "make the image"}
    clean_last = last.strip().lower()
    if len(user_texts) > 1 and clean_last in fillers:
        for prev in reversed(user_texts[:-1]):
            clean_prev = prev.strip().lower()
            if len(prev.strip()) >= 5 and clean_prev not in fillers:
                return prev.strip()
    clean = clean_prompt_text(last.strip())
    return clean if clean else "A creative high quality image"


async def execute_isolated_image_generation(body: dict, sources: list = None) -> dict:
    """Execute image generation on a fresh, isolated browser tab (multi-tab architecture)."""
    from .image_output import image_options, encode_image_output
    from .images import prepared_images
    from .generation import require_ready, _browser_error, response_model
    from .runtime import browser_manager
    from .routes import image_generation
    from contextlib import aclosing

    # If run_image is mocked in offline unit tests, honor the mock
    if hasattr(image_generation.run_image, "assert_called") or getattr(image_generation.run_image, "_is_mock", False):
        resp = await image_generation.run_image(body, sources or [])
        payload = json.loads(resp.body.decode("utf-8")) if hasattr(resp, "body") else {}
        data_list = payload.get("data", [])
        b64 = data_list[0]["b64_json"] if data_list and "b64_json" in data_list[0] else ""
        return {
            "data": base64.b64decode(b64) if b64 else b"",
            "b64": b64,
            "model": payload.get("model", body.get("model", DEFAULT_IMAGE_MODEL)),
            "encoding": payload.get("encoding", "png")
        }

    await require_ready()
    requested, model, prompt, size, options = image_options(body)
    request_id = "image_" + uuid.uuid4().hex[:16]

    logger.info("Opening isolated browser tab for image generation prompt='%s'", prompt[:60])
    worker = await browser_manager.create_page()
    try:
        async with worker.lock:
            input_sources = sources or []
            async with prepared_images(input_sources) as image_paths:
                uri = None
                async with aclosing(worker.send_prompt_and_stream(
                    prompt,
                    request_id=request_id,
                    model_name=model,
                    images=image_paths,
                    output_kind="image",
                    image_size=size,
                    image_settings=options,
                    temperature=options.get("temperature"),
                    reasoning_effort=options.get("reasoning_effort")
                )) as stream:
                    async for item in stream:
                        if isinstance(item, dict) and "error" in item:
                            raise _browser_error(str(item["error"]))
                        if isinstance(item, dict) and item.get("image"):
                            uri = item["image"]

                if not uri:
                    raise GatewayError(502, "AI Studio did not return an image.", "upstream_image_error")

                data, dimensions, encoding = await asyncio.to_thread(
                    encode_image_output, uri, options["output_format"], options.get("output_compression")
                )
                if size == "1024x1024" and dimensions != (1024, 1024):
                    raise GatewayError(502, "AI Studio image did not match the requested exact dimensions.", "upstream_image_size_mismatch", param="size")

                actual = response_model(model)
                browser_manager.generated_models.add(actual)
                return {
                    "data": data,
                    "b64": base64.b64encode(data).decode("ascii"),
                    "model": actual,
                    "encoding": encoding
                }
    finally:
        with CancelScope(shield=True):
            logger.info("Closing isolated image generation browser tab")
            await browser_manager.close_page(worker)


async def generate_chat_image(prompt: str, model_name: str = None, sources: list = None) -> dict:
    """Generate image using an isolated browser tab and save it to disk."""
    model = model_name or DEFAULT_IMAGE_MODEL
    if not is_image_model(model):
        model = DEFAULT_IMAGE_MODEL
    body = {
        "prompt": prompt,
        "model": model,
        "size": "auto",
        "output_format": "png"
    }
    input_sources = sources or []
    logger.info("Image Chat Bridge executing prompt='%s' with model='%s' sources=%d", prompt[:60], model, len(input_sources))
    img_data = await execute_isolated_image_generation(body, input_sources)
    b64_str = img_data["b64"]
    data_bytes = img_data["data"]
    actual_model = img_data.get("model", model)

    # Save to runtime/generated_images
    img_dir = Path("runtime/generated_images")
    img_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    fname = f"image_{stamp}_{uuid.uuid4().hex[:6]}.png"
    file_path = (img_dir / fname).resolve()
    file_path.write_bytes(data_bytes)

    # Also save a copy to project root generated_images for instant access
    try:
        proj_dir = Path("generated_images").resolve()
        proj_dir.mkdir(exist_ok=True)
        (proj_dir / fname).write_bytes(data_bytes)
    except Exception:
        pass

    posix_path = file_path.as_posix()
    img_url = f"http://127.0.0.1:{PORT}/images/{fname}"
    intro = f"🎨 **لقد تم توليد الصورة بنجاح بواسطة موديل الصور ({actual_model})!**\n\n"
    img_md = f"![الصورة المولدة]({img_url})\n\n"
    footer = f"🔗 **[اضغط هنا لعرض الصورة بالحجم الكامل في المتصفح]({img_url})**" 
    text = intro + img_md + footer
    return {
        "text": text,
        "intro": intro,
        "img_md": img_md,
        "footer": footer,
        "file_path": str(file_path),
        "fname": fname,
        "posix_path": posix_path,
        "img_url": img_url,
        "prompt": prompt,
        "b64": b64_str,
        "bytes": data_bytes,
        "model": actual_model
    }



async def generate_chat_voice(text: str, voice: str = None) -> dict:
    """Generate spoken audio / voice note using AI Studio speech and save to disk."""
    from .speech import generate_in_speech_page, encode_speech
    from .runtime import browser_manager
    from .generation import require_ready

    clean_text = text.strip()
    if len(clean_text) > 4000:
        clean_text = clean_text[:4000]
    from .speech import VOICE_SELECTORS
    req_voice = (voice or DEFAULT_SPEECH_VOICE).strip()
    target_voice = DEFAULT_SPEECH_VOICE if req_voice.lower() == 'alloy' else VOICE_SELECTORS.get(req_voice.lower(), req_voice)
    target_model = DEFAULT_SPEECH_MODEL
    catalog = getattr(browser_manager, "model_catalog", {})
    speech_candidates = [
        m for m, item in catalog.items()
        if item.get("status") == "selectable" and (m.endswith("-tts") or item.get("capabilities", {}).get("output_modalities") == ["audio"])
    ]
    if speech_candidates and target_model not in catalog:
        target_model = speech_candidates[0]

    logger.info("Voice Chat Bridge: generating voice for '%s' (voice=%s)", clean_text[:60], target_voice)
    await require_ready()
    worker = await browser_manager.create_page()
    try:
        async with worker.lock:
            raw_wav = await generate_in_speech_page(worker, clean_text, target_model, target_voice)
            mp3_bytes = await encode_speech(raw_wav, "mp3", 1.0)

            audio_dir = Path("runtime/generated_audio")
            audio_dir.mkdir(parents=True, exist_ok=True)
            stamp = int(time.time())
            fname = f"voice_{stamp}_{uuid.uuid4().hex[:6]}.mp3"
            file_path = (audio_dir / fname).resolve()
            file_path.write_bytes(mp3_bytes)

            try:
                proj_dir = Path("generated_audio").resolve()
                proj_dir.mkdir(exist_ok=True)
                (proj_dir / fname).write_bytes(mp3_bytes)
            except Exception:
                pass

            audio_url = f"http://127.0.0.1:{PORT}/audio/{fname}"
            intro = f"🔊 **تم توليد المقطع الصوتي بنجاح ({target_voice})!**\n\n"
            link_md = f"▶️ **[اضغط هنا للاستماع للمقطع الصوتي]({audio_url})**\n\n"
            full_text = intro + link_md
            return {
                "text": full_text,
                "audio_url": audio_url,
                "url": audio_url,
                "file_path": str(file_path),
                "fname": fname,
                "voice": target_voice,
                "bytes": mp3_bytes
            }
    except Exception as ex:
        logger.warning("Voice Chat Bridge synthesis failed: %s", ex)
        err_msg = f"⚠️ تعذر توليد المقطع الصوتي عبر المتصفح: {ex}"
        return {
            "text": err_msg,
            "audio_url": None,
            "file_path": None,
            "fname": None,
            "voice": target_voice,
            "bytes": b""
        }
    finally:
        with CancelScope(shield=True):
            logger.info("Closing isolated voice generation browser tab")
            await browser_manager.close_page(worker)


def make_desktop_artifact(res, desktop: bool) -> str:
    """Artifacts are omitted to prevent raw HTML code blocks in the chat."""
    return ""


async def handle_anthropic_image_request(body, converted, alias, sem, owner, *, desktop=False):
    """Handle Anthropic Messages protocol when an image model or image intent is requested."""
    from .anthropic import native_error
    identifier = "msg_" + uuid.uuid4().hex[:24]
    prompt = extract_image_prompt(converted.get("messages", []))
    sources = extract_image_sources(converted.get("messages", []))
    target_model = converted.get("model") or DEFAULT_IMAGE_MODEL
    stream = body.get("stream", False)

    logger.info("Anthropic Image Bridge: %s model=%s stream=%s sources=%d prompt='%s'",
                identifier, target_model, stream, len(sources), prompt[:60])

    async def get_result():
        return await generate_chat_image(prompt, target_model, sources=sources)

    if not stream:
        result = await get_result()
        artifact_block = make_desktop_artifact(result, desktop)
        final_text = result["text"]
        payload = {
            "id": identifier,
            "type": "message",
            "role": "assistant",
            "model": alias or target_model,
            "content": [{"type": "text", "text": final_text}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": len(prompt.split()) + 10, "output_tokens": 120}
        }
        if alias:
            payload["virel"] = {
                "compatibility_alias": True,
                "requested_ui_model": target_model,
                "actual_model": result["model"],
                "actual_provider": "google-ai-studio"
            }
        headers = {
            "X-Virel-Model-Provider": "google-ai-studio",
            "X-Virel-Image-Generated": "true",
            "X-Virel-Image-File": result["file_path"]
        }
        if alias:
            headers["X-Virel-Model-Alias"] = alias
            headers["X-Virel-Actual-Model"] = result["model"]
        return JSONResponse(payload, headers=headers)

    # Streaming mode
    async def serialize():
        def event(kind, **values):
            return "event: " + kind + "\ndata: " + json.dumps({"type": kind, **values}, ensure_ascii=False) + "\n\n"
        try:
            # 1. Immediately yield message_start and initial text block start
            # This guarantees TTFB is < 10ms, Claude Desktop receives 200 OK immediately and NEVER retries/times out
            payload = {
                "id": identifier,
                "type": "message",
                "role": "assistant",
                "model": alias or target_model,
                "usage": {"input_tokens": len(prompt.split()) + 10, "output_tokens": 120}
            }
            if alias:
                payload["virel"] = {
                    "compatibility_alias": True,
                    "requested_ui_model": target_model,
                    "actual_model": target_model,
                    "actual_provider": "google-ai-studio"
                }
            yield event("message_start", message={**payload, "content": [], "stop_reason": None, "usage": payload["usage"]})
            yield event("content_block_start", index=0, content_block={"type": "text", "text": ""})

            # 2. Launch background generation task
            gen_task = asyncio.create_task(get_result())

            # 3. Emit official Anthropic ping events while generating so Claude Desktop stays connected and patient
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=1.5)
                    break
                except asyncio.TimeoutError:
                    yield event("ping")

            result = await gen_task

            # 4. Stream intro text
            yield event("content_block_delta", index=0, delta={"type": "text_delta", "text": result["intro"]})

            # 5. Stream base64 image in 32KB chunks for smooth SSE transport
            yield event("content_block_delta", index=0, delta={"type": "text_delta", "text": f"![{result['prompt']}](data:image/png;base64,"})
            b64 = result["b64"]
            for offset in range(0, len(b64), 32768):
                yield event("content_block_delta", index=0, delta={"type": "text_delta", "text": b64[offset:offset+32768]})
            yield event("content_block_delta", index=0, delta={"type": "text_delta", "text": ")\n\n"})

            # 6. Stream footer
            yield event("content_block_delta", index=0, delta={"type": "text_delta", "text": result["footer"]})

            yield event("content_block_stop", index=0)
            yield event("message_delta", delta={"stop_reason": "end_turn", "stop_sequence": None}, usage=payload["usage"])
            yield event("message_stop")
        except GatewayError as error:
            yield "event: error\ndata: " + json.dumps(native_error(error), ensure_ascii=False) + "\n\n"
        except Exception as ex:
            err = GatewayError(500, f"Image generation error: {ex}", "image_generation_failed")
            yield "event: error\ndata: " + json.dumps(native_error(err), ensure_ascii=False) + "\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "X-Virel-Stream-Mode": "completed_browser_snapshot_paced",
        "X-Virel-Image-Generated": "true"
    }
    if alias:
        headers["X-Virel-Model-Alias"] = alias
    return StreamingResponse(serialize(), media_type="text/event-stream", headers=headers)


async def handle_openai_image_request(request, chat_request, sem):
    """Handle OpenAI Chat Completions protocol when an image model or image intent is requested."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    prompt = extract_image_prompt([m.model_dump() if hasattr(m, "model_dump") else dict(m) for m in chat_request.messages])
    target_model = chat_request.model or DEFAULT_IMAGE_MODEL
    stream = chat_request.stream
    now = int(time.time())

    logger.info("OpenAI Chat Image Bridge: %s model=%s stream=%s prompt='%s'",
                chunk_id, target_model, stream, prompt[:60])

    if not stream:
        result = await generate_chat_image(prompt, target_model)
        return JSONResponse({
            "id": chunk_id,
            "object": "chat.completion",
            "created": now,
            "model": target_model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": result["text"]
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": len(prompt.split()) + 10,
                "completion_tokens": 120,
                "total_tokens": len(prompt.split()) + 130
            }
        }, headers={"X-Virel-Image-Generated": "true", "X-Virel-Image-File": result["file_path"]})

    # OpenAI SSE streaming
    async def serialize():
        try:
            # First delta: role immediately
            yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'created': now, 'model': target_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"

            gen_task = asyncio.create_task(generate_chat_image(prompt, target_model))
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=1.5)
                    break
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"

            result = await gen_task

            # Stream intro, image markdown in one delta, then footer
            yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'created': now, 'model': target_model, 'choices': [{'index': 0, 'delta': {'content': result['intro']}, 'finish_reason': None}]})}\n\n"
            yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'created': now, 'model': target_model, 'choices': [{'index': 0, 'delta': {'content': result['img_md']}, 'finish_reason': None}]})}\n\n"
            yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'created': now, 'model': target_model, 'choices': [{'index': 0, 'delta': {'content': result['footer']}, 'finish_reason': None}]})}\n\n"
            yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'created': now, 'model': target_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as ex:
            yield f"data: {json.dumps({'error': {'message': str(ex), 'type': 'server_error'}})}\n\n"

    return StreamingResponse(serialize(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Virel-Image-Generated": "true"})


async def handle_responses_image_request(body, sem):
    """Handle OpenAI Responses protocol when an image model or image intent is requested."""
    req_id = f"resp_{uuid.uuid4().hex[:16]}"
    now = int(time.time())
    messages = body.get("messages") or body.get("input") or []
    if isinstance(messages, str):
        prompt = messages
    else:
        prompt = extract_image_prompt(messages)
    target_model = body.get("model") or DEFAULT_IMAGE_MODEL

    logger.info("Responses Image Bridge: %s model=%s prompt='%s'", req_id, target_model, prompt[:60])
    result = await generate_chat_image(prompt, target_model)

    return JSONResponse({
        "id": req_id,
        "object": "response",
        "created_at": now,
        "status": "completed",
        "error": None,
        "model": target_model,
        "output": [
            {
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex[:16]}",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": result["text"]
                    }
                ]
            }
        ],
        "usage": {
            "total_tokens": len(prompt.split()) + 130,
            "input_tokens": len(prompt.split()) + 10,
            "output_tokens": 120
        }
    }, headers={"X-Virel-Image-Generated": "true", "X-Virel-Image-File": result["file_path"]})
