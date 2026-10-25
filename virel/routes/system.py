"""Health, model catalog, diagnostics, and shutdown endpoints."""

import asyncio
import os
import re
import time
from fastapi import APIRouter, Depends
from fastapi.responses import Response, HTMLResponse

from ..auth import verify_api_key
from ..config import BASE_DIR, RUNTIME_DIR, SESSION_DATA_PATH, HEADLESS, DEFAULT_MODEL, THINKING_MODE, PORT, RATE_LIMIT
from ..errors import GatewayError
from ..runtime import browser_manager

DASHBOARD_HTML_PATH = os.path.join(BASE_DIR, "virel", "dashboard.html")

router = APIRouter()


@router.get("/debug/state", dependencies=[Depends(verify_api_key)])
async def debug_state(page_id: str | None = None):
    browser = browser_manager.diagnostic(page_id)
    if not browser.page or browser.page.is_closed():
        return {"error": "no page"}
    body_text = await browser.page.evaluate("() => (document.body.innerText || '').slice(0, 3000)")
    html_sample = await browser.page.evaluate("() => (document.body.innerHTML || '').slice(0, 3000)")
    turns_info = await browser.page.evaluate('''() => {
        const turns = Array.from(document.querySelectorAll('ms-chat-turn, .chat-turn'));
        return turns.map((t, idx) => ({
            index: idx,
            tag: t.tagName,
            cls: t.className,
            role: t.getAttribute('data-turn-role'),
            author_elements: Array.from(t.querySelectorAll('*')).filter(e => {
                const txt = (e.innerText || '').trim();
                return txt === 'User' || txt === 'Model' || txt.startsWith('User ') || txt.startsWith('Model ');
            }).map(e => ({ tag: e.tagName, cls: e.className, text: e.innerText })),
            has_thumb: t.querySelector('mat-icon, [aria-label*="thumb" i]') !== null,
            preview: (t.innerText || '').slice(0, 150)
        }));
    }''')
    await browser.page.screenshot(path=f"{RUNTIME_DIR}/debug_state_{browser.request_id}.png")
    return {"body_text": body_text, "turns": turns_info, "html": html_sample}


@router.get("/health")
async def health_check():
    """Returns gateway status, browser state, and configuration."""
    from ..runtime import account_manager
    has_session = os.path.exists(SESSION_DATA_PATH)
    return {
        "status": "ok",
        "gateway": "Virel AI (AIStudio Web Hook)",
        "version": "0.1.1",
        "accounts": account_manager.stats(),
        "browser_ready": browser_manager.is_ready,
        "browser_state_scope": "control_page",
        "requests": browser_manager.stats(),
        "session_file_exists": has_session,
        "headless": HEADLESS,
        "default_model": DEFAULT_MODEL,
        "thinking_mode": THINKING_MODE,
        "active_model": browser_manager.active_model,
        "model_verified": getattr(browser_manager, "model_verified", False),
        "active_thinking": browser_manager.active_thinking,
        "thinking_verified": getattr(browser_manager, "thinking_verified", False),
        "active_temperature": browser_manager.active_temperature,
        "temperature_verified": browser_manager.temperature_verified,
        "url_context_enabled": browser_manager.url_context_enabled,
        "url_context_verified": browser_manager.url_context_verified,
        "google_search_enabled": getattr(browser_manager, "google_search_enabled", False),
        "search_verified": getattr(browser_manager, "search_verified", False),
        "clear_chat_on_request": True,
        "port": PORT,
        "rate_limit": RATE_LIMIT
    }


@router.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the Virel AI Control Plane Web Dashboard."""
    if not os.path.isfile(DASHBOARD_HTML_PATH):
        raise GatewayError(404, "Dashboard UI file (virel/dashboard.html) not found.", "dashboard_not_found")
    with open(DASHBOARD_HTML_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, headers={"Cache-Control": "no-cache"})


@router.get("/accounts", dependencies=[Depends(verify_api_key)])
async def get_accounts_status():
    """Returns status, active account, and cooldowns across all configured Google accounts."""
    from ..runtime import account_manager
    return account_manager.stats()


@router.post("/accounts/reset", dependencies=[Depends(verify_api_key)])
async def reset_accounts_status():
    """Reset cooldown timers and statuses on all accounts back to ready."""
    from ..runtime import account_manager
    account_manager.reset_all_cooldowns()
    return {"message": "All account cooldowns have been reset to ready.", "accounts": account_manager.stats()}


@router.get("/images/{filename}")
@router.get("/claude/images/{filename}")
async def serve_image(filename: str):
    """Serve locally generated chat images for web views and desktop markdown previews."""
    if not re.fullmatch(r"image_[0-9]+_[0-9a-fA-F]+\.(?:png|jpg|jpeg|webp)", filename):
        raise GatewayError(400, "Invalid image filename.", "invalid_request")
    p1 = os.path.join(RUNTIME_DIR, "generated_images", filename)
    p2 = os.path.join(BASE_DIR, "generated_images", filename)
    target = p1 if os.path.isfile(p1) else (p2 if os.path.isfile(p2) else None)
    if not target:
        raise GatewayError(404, "Image not found.", "image_not_found")
    with open(target, "rb") as f:
        data = f.read()
    mime = "image/png" if filename.endswith(".png") else ("image/webp" if filename.endswith(".webp") else "image/jpeg")
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
        }
    )


@router.get("/audio/{filename}")
@router.get("/claude/audio/{filename}")
async def serve_audio(filename: str):
    """Serve locally generated chat audio / voice files for desktop and web playback."""
    if not re.fullmatch(r"voice_[0-9]+_[0-9a-fA-F]+\.(?:mp3|wav|ogg|flac|aac)", filename):
        raise GatewayError(400, "Invalid audio filename.", "invalid_request")
    p1 = os.path.join(RUNTIME_DIR, "generated_audio", filename)
    p2 = os.path.join(BASE_DIR, "generated_audio", filename)
    target = p1 if os.path.isfile(p1) else (p2 if os.path.isfile(p2) else None)
    if not target:
        raise GatewayError(404, "Audio file not found.", "audio_not_found")
    with open(target, "rb") as f:
        data = f.read()
    mime = "audio/mpeg" if filename.endswith(".mp3") else ("audio/wav" if filename.endswith(".wav") else "audio/ogg")
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
        }
    )



@router.get("/v1/models", dependencies=[Depends(verify_api_key)])
@router.get("/models", dependencies=[Depends(verify_api_key)])
async def list_models(refresh: bool = False):
    """Last complete UI observation; explicit refresh never interrupts generation."""
    from ..errors import GatewayError
    if refresh:
        if not browser_manager.is_ready:
            raise GatewayError(503, 'AI Studio is not ready.', 'browser_not_ready')
        if browser_manager.lock.locked():
            raise GatewayError(429, 'Browser is processing another request.', 'concurrency_limit')
        async with browser_manager.lock:
            await browser_manager.refresh_model_catalog()
    records = []
    if browser_manager.is_ready and browser_manager.model_catalog_observed:
        for item in browser_manager.model_catalog.values():
            if item['status'] != 'selectable':
                continue
            actual = item.get('resolved_id', item['id'])
            records.append({'id': item['id'], 'object': 'model', 'created': browser_manager.catalog_observed_at,
                'owned_by': 'google-ai-studio-web', 'display_name': item['display_name'],
                'capabilities': item['capabilities'], 'virel': {'source': 'ai_studio_ui',
                    'observed_at': browser_manager.catalog_observed_at, 'generation_verified': actual in browser_manager.generated_models,
                    'resolved_id': item.get('resolved_id')}})
    return {'object': 'list', 'data': records}


@router.get("/debug_dom", dependencies=[Depends(verify_api_key)])
async def debug_dom(page_id: str | None = None):
    browser = browser_manager.diagnostic(page_id)
    if not browser.page or browser.page.is_closed():
        return {"error": "no page"}
    data = await browser.page.evaluate('''() => {
        const matSelects = Array.from(document.querySelectorAll('mat-select')).map(s => ({
            aria: s.getAttribute('aria-label') || '',
            text: (s.innerText || '').trim(),
            html: s.outerHTML.slice(0, 100)
        }));
        const buttons = Array.from(document.querySelectorAll('button')).map(b => ({
            aria: b.getAttribute('aria-label') || '',
            text: (b.innerText || '').trim(),
            cls: b.className || ''
        })).filter(b => b.aria || b.text);
        return {
            url: window.location.href,
            title: document.title,
            matSelects: matSelects,
            buttonsCount: buttons.length,
            modelKeywords: buttons.filter(b => /gemini|flash|pro|model|think/i.test(b.aria + ' ' + b.text))
        };
    }''')
    return data


@router.get("/shutdown", dependencies=[Depends(verify_api_key)])
@router.post("/shutdown", dependencies=[Depends(verify_api_key)])
async def shutdown_server():
    async def _close_and_exit():
        await asyncio.sleep(0.3)
        try:
            await browser_manager.stop()
        finally:
            os._exit(0)
    asyncio.create_task(_close_and_exit())
    return {"status": "shutting down", "port": PORT}
