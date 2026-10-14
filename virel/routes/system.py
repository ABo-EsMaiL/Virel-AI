"""Health, model catalog, diagnostics, and shutdown endpoints."""

import asyncio
import os
import time
from fastapi import APIRouter, Depends

from ..auth import verify_api_key
from ..config import SESSION_DATA_PATH, CHROME_PROFILE_DIR, HEADLESS, DEFAULT_MODEL, THINKING_MODE, CLEAR_CHAT_ON_REQUEST, PORT, RATE_LIMIT
from ..runtime import browser_manager

router = APIRouter()


@router.get("/debug/state")
async def debug_state():
    if not browser_manager.page or browser_manager.page.is_closed():
        return {"error": "no page"}
    body_text = await browser_manager.page.evaluate("() => (document.body.innerText || '').slice(0, 3000)")
    html_sample = await browser_manager.page.evaluate("() => (document.body.innerHTML || '').slice(0, 3000)")
    turns_info = await browser_manager.page.evaluate('''() => {
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
    await browser_manager.page.screenshot(path="debug_state.png")
    return {"body_text": body_text, "turns": turns_info, "html": html_sample}


@router.get("/health")
async def health_check():
    """Returns gateway status, browser state, and configuration."""
    has_session = os.path.exists(SESSION_DATA_PATH)
    return {
        "status": "ok",
        "gateway": "Virel (AIStudio Web Hook)",
        "version": "0.1.0",
        "browser_ready": browser_manager.is_ready,
        "session_file_exists": has_session,
        "headless": HEADLESS,
        "profile_dir": CHROME_PROFILE_DIR,
        "default_model": DEFAULT_MODEL,
        "thinking_mode": THINKING_MODE,
        "active_model": browser_manager.active_model,
        "model_verified": getattr(browser_manager, "model_verified", False),
        "active_thinking": browser_manager.active_thinking,
        "thinking_verified": getattr(browser_manager, "thinking_verified", False),
        "google_search_enabled": getattr(browser_manager, "google_search_enabled", False),
        "search_verified": getattr(browser_manager, "search_verified", False),
        "clear_chat_on_request": CLEAR_CHAT_ON_REQUEST,
        "port": PORT,
        "rate_limit": RATE_LIMIT
    }


@router.get("/v1/models", dependencies=[Depends(verify_api_key)])
async def list_models():
    """Lists supported models in standard OpenAI format."""
    now = int(time.time())
    models = [
        "gemini-3.8-flash",
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash"
    ]
    return {
        "object": "list",
        "data": [
            {
                "id": m,
                "object": "model",
                "created": now,
                "owned_by": "google-ai-studio-web"
            }
            for m in models
        ]
    }


@router.get("/debug_dom")
async def debug_dom():
    if not browser_manager.page or browser_manager.page.is_closed():
        return {"error": "no page"}
    data = await browser_manager.page.evaluate('''() => {
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


@router.get("/shutdown")
@router.post("/shutdown")
async def shutdown_server():
    async def _close_and_exit():
        await asyncio.sleep(0.3)
        try:
            await browser_manager.stop()
        finally:
            os._exit(0)
    asyncio.create_task(_close_and_exit())
    return {"status": "shutting down", "port": PORT}
