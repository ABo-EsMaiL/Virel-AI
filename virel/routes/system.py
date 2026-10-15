"""Health, model catalog, diagnostics, and shutdown endpoints."""

import asyncio
import os
import time
from fastapi import APIRouter, Depends

from ..auth import verify_api_key
from ..config import RUNTIME_DIR, SESSION_DATA_PATH, HEADLESS, DEFAULT_MODEL, THINKING_MODE, PORT, RATE_LIMIT
from ..runtime import browser_manager

router = APIRouter()


@router.get("/debug/state", dependencies=[Depends(verify_api_key)])
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
    await browser_manager.page.screenshot(path=f"{RUNTIME_DIR}/debug_state.png")
    return {"body_text": body_text, "turns": turns_info, "html": html_sample}


@router.get("/health")
async def health_check():
    """Returns gateway status, browser state, and configuration."""
    has_session = os.path.exists(SESSION_DATA_PATH)
    return {
        "status": "ok",
        "gateway": "Virel AI (AIStudio Web Hook)",
        "version": "0.1.1",
        "browser_ready": browser_manager.is_ready,
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


@router.get("/v1/models", dependencies=[Depends(verify_api_key)])
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
