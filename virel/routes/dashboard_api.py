"""Control Plane Dashboard REST APIs, Root Architecture Portal (/), Live Browser WebSocket (/ws/browser), and Live Logs WebSocket (/ws/logs)."""

import asyncio
import base64
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus
from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from .. import config
from ..auth import verify_api_key, verify_native_key
from ..errors import GatewayError
from ..models import IMAGE_MODEL_ICONS
from ..runtime import account_manager, browser_manager
from ..telemetry import (
    EnvConfigManager,
    agent_keys,
    capture_incident_screenshot,
    enforce_media_storage_limit,
    get_media_storage_stats,
    list_incidents,
    log_hub,
    store as telemetry_store,
)

logger = logging.getLogger("virel.webhook")
router = APIRouter()

ASSETS_DIR = os.path.join(config.BASE_DIR, "assets")
README_PATH = os.path.join(config.BASE_DIR, "README.md")


@router.get("/assets/{filename}")
async def serve_asset(filename: str):
    """Serve brand logo and workflow diagrams from ./assets/."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.(?:png|jpg|jpeg|svg|webp|gif|ico)", filename):
        raise GatewayError(400, "Invalid asset filename.", "invalid_request")
    target = os.path.join(ASSETS_DIR, filename)
    if not os.path.isfile(target):
        raise GatewayError(404, "Asset not found.", "asset_not_found")
    return FileResponse(target, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/", response_class=HTMLResponse)
async def root_portal():
    """Root landing page directing users to /dashboard while rendering README & System Architecture."""
    readme_text = ""
    if os.path.isfile(README_PATH):
        try:
            with open(README_PATH, "r", encoding="utf-8") as f:
                readme_text = f.read()
        except Exception:
            readme_text = "# Virel AI\nCould not read README.md."

    readme_json = json.dumps(readme_text)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Virel AI — Gateway Portal & Architecture</title>
  <link rel="icon" type="image/png" href="/assets/logo.png" />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <style>
    :root {{
      --bg: #06090e;
      --surface: #0d131c;
      --border: rgba(16, 185, 129, 0.22);
      --text: #f1f5f9;
      --muted: #94a3b8;
      --accent: #10b981;
      --cyan: #06b6d4;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: radial-gradient(circle at 50% 0%, rgba(16, 185, 129, 0.12), transparent 55%), var(--bg);
      color: var(--text);
      font-family: 'Inter', sans-serif;
      line-height: 1.6;
      padding-bottom: 60px;
    }}
    .hero-redirect {{
      max-width: 1180px;
      margin: 28px auto;
      padding: 28px 32px;
      background: linear-gradient(135deg, rgba(13, 19, 28, 0.95), rgba(6, 78, 59, 0.28));
      border: 1px solid var(--border);
      border-radius: 16px;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.55), 0 0 30px rgba(16, 185, 129, 0.12);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      flex-wrap: wrap;
    }}
    .hero-left {{
      display: flex;
      align-items: center;
      gap: 20px;
    }}
    .hero-left img {{
      width: 72px;
      height: 72px;
      border-radius: 16px;
      box-shadow: 0 0 25px rgba(16, 185, 129, 0.4);
    }}
    .hero-title {{
      font-size: 22px;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    .hero-sub {{
      color: var(--muted);
      font-size: 14px;
      margin-top: 4px;
    }}
    .cta-btn {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      background: linear-gradient(135deg, var(--accent), var(--cyan));
      color: #04130e;
      font-weight: 700;
      font-size: 14px;
      padding: 13px 24px;
      border-radius: 10px;
      text-decoration: none;
      box-shadow: 0 0 25px rgba(16, 185, 129, 0.4);
      transition: transform 0.2s, box-shadow 0.2s;
    }}
    .cta-btn:hover {{
      transform: translateY(-2px);
      box-shadow: 0 0 35px rgba(6, 182, 212, 0.65);
    }}
    .container {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 0 20px;
      display: flex;
      flex-direction: column;
      gap: 28px;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid rgba(148, 163, 184, 0.14);
      border-radius: 14px;
      padding: 28px;
    }}
    .card-title {{
      font-size: 16px;
      font-weight: 600;
      color: var(--accent);
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.12);
      padding-bottom: 12px;
    }}
    .markdown-body {{ color: #e2e8f0; font-size: 14.5px; }}
    .markdown-body h1, .markdown-body h2, .markdown-body h3 {{ margin: 22px 0 12px; color: #fff; }}
    .markdown-body p {{ margin-bottom: 12px; }}
    .markdown-body pre {{
      background: #06080c;
      border: 1px solid rgba(148, 163, 184, 0.16);
      padding: 14px;
      border-radius: 8px;
      overflow-x: auto;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12.5px;
      margin: 12px 0;
    }}
    .markdown-body code {{
      font-family: 'JetBrains Mono', monospace;
      background: rgba(16, 185, 129, 0.12);
      color: #34d399;
      padding: 2px 5px;
      border-radius: 4px;
    }}
    .markdown-body pre code {{ background: transparent; color: #e2e8f0; padding: 0; }}
    .markdown-body table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
    .markdown-body th, .markdown-body td {{
      border: 1px solid rgba(148, 163, 184, 0.18);
      padding: 10px 12px;
      text-align: left;
    }}
    .markdown-body th {{ background: rgba(16, 185, 129, 0.08); }}
    .markdown-body img {{ max-width: 100%; border-radius: 10px; }}
    .markdown-body details {{
      background: rgba(255,255,255,0.02);
      border: 1px solid rgba(148, 163, 184, 0.15);
      border-radius: 8px;
      padding: 10px 14px;
      margin: 10px 0;
    }}
    .markdown-body summary {{ cursor: pointer; font-weight: 600; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="hero-redirect">
      <div class="hero-left">
        <img src="/assets/logo.png" alt="Virel AI" />
        <div>
          <div class="hero-title">Virel AI — Gateway Documentation & Root Portal</div>
          <div class="hero-sub">The interactive Control Plane Dashboard (<code>/dashboard</code>) is the primary interface for managing accounts, live browser sessions, .env settings, and token telemetry.</div>
        </div>
      </div>
      <a href="/dashboard" class="cta-btn">
        <span>Open Control Plane Dashboard</span>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
      </a>
    </div>

    <div class="card">
      <div class="card-title">Control Plane & Telemetry System Architecture</div>
      <pre class="mermaid">
flowchart TB
    subgraph Frontend["Frontend Layer (Motion Graphics UI - Dark & Light Mode)"]
        UI["virel/dashboard.html + /assets/logo.png"]
        T1["1. Command Center & Engine Power Controls"]
        T2["2. Token Analytics (Day/Week/Month/Year/All + Per-Account)"]
        T3["3. Agent Connect Hub (Sub-Keys + Setup Guides)"]
        T4["4. Live Browser Studio (Interactive CDP WebSocket for Sign-In/2FA)"]
        T5["5. Two-Way Live .env Configurator (Switches & Chips)"]
        T6["6. Live Logs, Blackbox Incidents (By Date) & Backup/Restore"]
        UI --> T1 & T2 & T3 & T4 & T5 & T6
    end

    subgraph API["Control Plane Router (virel/routes/dashboard_api.py)"]
        REST["REST Endpoints (/api/dashboard/*)"]
        WS_BR["WebSocket (/ws/browser) -> Interactive Chromium Stream"]
        WS_LG["WebSocket (/ws/logs) -> Real-time Server Log Stream"]
    end

    subgraph Core["Telemetry & Storage Engine (virel/telemetry.py)"]
        DB[("SQLite: runtime/telemetry.db")]
        KEYS["Multi-Agent API Key Allowlist"]
        ENV["Two-Way .env Parser & Live Sync"]
        INC["Blackbox Recorder (runtime/incidents/YYYY-MM-DD/)"]
        MEDIA["Media Storage Guard (1GB Auto-Evict / Offload)"]
    end

    Frontend <==> REST & WS_BR & WS_LG
    REST <==> DB & KEYS & ENV & INC & MEDIA
      </pre>
    </div>

    <div class="card">
      <div class="card-title">Repository README.md</div>
      <div id="readme-content" class="markdown-body"></div>
    </div>
  </div>

  <script>
    const rawMd = {readme_json};
    const renderer = new marked.Renderer();
    const origCode = renderer.code.bind(renderer);
    renderer.code = function(code, lang) {{
      const text = typeof code === 'object' ? code.text : code;
      const language = typeof code === 'object' ? code.lang : lang;
      if (language === 'mermaid') {{
        return '<pre class="mermaid">' + text + '</pre>';
      }}
      return origCode(code, lang);
    }};
    document.getElementById('readme-content').innerHTML = marked.parse(rawMd, {{ renderer }});
    mermaid.initialize({{ startOnLoad: true, theme: 'dark' }});
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/api/dashboard/overview")
async def dashboard_overview():
    """Return comprehensive live state for the Control Plane Dashboard (no auth required for basic status check; sensitive actions require verify_api_key)."""
    owner = browser_manager._owner
    page = owner.page if owner else None
    current_url = ""
    needs_login = getattr(owner, "needs_login", False)
    engine_running = bool(owner and owner.context and not getattr(owner, "context_closed", True) and not owner.is_shutting_down)
    if page and not page.is_closed():
        try:
            current_url = page.url or ""
            if "accounts.google.com" in current_url or "welcome" in current_url:
                needs_login = True
        except Exception:
            pass

    return {
        "status": "ok",
        "version": "0.2.0",
        "engine_running": engine_running,
        "browser_ready": bool(browser_manager.is_ready and engine_running and not needs_login),
        "needs_google_login": needs_login,
        "control_page_url": current_url,
        "session_file_exists": os.path.exists(config.SESSION_DATA_PATH),
        "auth_required": bool(config.API_KEY or agent_keys.keys),
        "active_model": browser_manager.active_model or config.DEFAULT_MODEL,
        "model_verified": getattr(browser_manager, "model_verified", False),
        "active_thinking": browser_manager.active_thinking or config.THINKING_MODE,
        "thinking_verified": getattr(browser_manager, "thinking_verified", False),
        "active_temperature": browser_manager.active_temperature,
        "temperature_verified": browser_manager.temperature_verified,
        "url_context_enabled": browser_manager.url_context_enabled,
        "url_context_verified": browser_manager.url_context_verified,
        "google_search_enabled": getattr(browser_manager, "google_search_enabled", False),
        "search_verified": getattr(browser_manager, "search_verified", False),
        "accounts": account_manager.stats(),
        "pool": browser_manager.stats(),
        "media_storage": get_media_storage_stats(),
        "incidents_count": len(list_incidents(limit=100)),
    }


@router.get("/api/dashboard/analytics")
async def dashboard_analytics(period: str = Query("today")):
    """Return SQLite token & request analytics across Today, Week, Month, Year, All-Time + Per-Account & Per-Agent."""
    data = await asyncio.to_thread(telemetry_store.query_analytics, period)
    return data


@router.get("/api/dashboard/config")
async def get_dashboard_config():
    """Read two-way live .env and runtime settings along with live categorized models & voices."""
    catalog = getattr(browser_manager, "model_catalog", {}) or {}

    observed_text = []
    observed_image = []
    observed_speech = []

    for item in catalog.values():
        if item.get("status") != "selectable":
            continue
        mid = item["id"]
        mname = item.get("display_name") or mid
        caps = item.get("capabilities", {})
        out_mods = caps.get("output_modalities") or []
        icon = caps.get("ui_category_icon", "")

        entry = {"id": mid, "name": f"{mname} ({mid})", "observed": True}
        if "image" in out_mods or icon in IMAGE_MODEL_ICONS or "image" in mid:
            observed_image.append(entry)
        elif "audio" in out_mods or icon == "audio_magic_eraser" or "-tts" in mid:
            observed_speech.append(entry)
        else:
            observed_text.append(entry)

    baseline_text = [
        {"id": "gemini-flash-latest", "name": "Gemini Flash Latest — Official Alias"},
        {"id": "gemini-pro-latest", "name": "Gemini Pro Latest — Official Alias"},
        {"id": "gemini-flash-lite-latest", "name": "Gemini Flash-Lite Latest — Official Alias"},
        {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash"},
        {"id": "gemini-3.8-pro", "name": "Gemini 3.8 Pro"},
        {"id": "gemini-3.1-pro-preview", "name": "Gemini 3.1 Pro Preview"},
        {"id": "gemini-3.1-flash-lite-preview", "name": "Gemini 3.1 Flash-Lite Preview"},
        {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro — Deep Reasoning & Coding"},
        {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash — Fast Multimodal & Thinking"},
        {"id": "gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash-Lite"},
        {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash"},
        {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro"},
        {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash"},
    ]

    baseline_image = [
        {"id": "gemini-3.1-flash-lite-image", "name": "Gemini 3.1 Flash-Lite Image — Nano Banana"},
        {"id": "gemini-2.5-flash-image-preview", "name": "Gemini 2.5 Flash Image Preview"},
        {"id": "gemini-2.0-flash-preview-image-generation", "name": "Gemini 2.0 Flash Image Generation"},
        {"id": "imagen-3.0-generate-002", "name": "Imagen 3.0 Generate 002 — High Fidelity"},
        {"id": "imagen-3.0-generate-001", "name": "Imagen 3.0 Generate 001"},
        {"id": "gpt-image-1", "name": "gpt-image-1 — OpenAI Compatible Alias"},
    ]

    baseline_speech = [
        {"id": "gemini-3.8-flash-tts", "name": "Gemini 3.8 Flash TTS — Default AI Studio Speech"},
        {"id": "gemini-3.8-flash-lite-tts", "name": "Gemini 3.8 Flash-Lite TTS"},
        {"id": "gemini-3.1-flash-lite-tts", "name": "Gemini 3.1 Flash-Lite TTS"},
        {"id": "gemini-2.5-flash-preview-tts", "name": "Gemini 2.5 Flash Preview TTS — Multi-Speaker & Expressive"},
        {"id": "gemini-2.5-pro-preview-tts", "name": "Gemini 2.5 Pro Preview TTS — Studio Quality"},
        {"id": "gemini-2.5-flash-tts", "name": "Gemini 2.5 Flash TTS"},
        {"id": "gemini-2.5-pro-tts", "name": "Gemini 2.5 Pro TTS"},
        {"id": "speech-latest", "name": "Speech Latest — Official Alias"},
        {"id": "tts-1", "name": "tts-1 — OpenAI Compatible Alias"},
        {"id": "tts-1-hd", "name": "tts-1-hd — OpenAI HD Alias"},
    ]

    baseline_voices = [
        {"id": "Fola", "name": "Fola — Default Warm & Natural", "category": "Google AI Studio"},
        {"id": "Bodi", "name": "Bodi — Deep & Resonant", "category": "Google AI Studio"},
        {"id": "Koda", "name": "Koda — Bright & Expressive", "category": "Google AI Studio"},
        {"id": "Lumi", "name": "Lumi — Soft & Clear", "category": "Google AI Studio"},
        {"id": "Mako", "name": "Mako — Calm & Authoritative", "category": "Google AI Studio"},
        {"id": "Sola", "name": "Sola — Cheerful & Dynamic", "category": "Google AI Studio"},
        {"id": "Zephyr", "name": "Zephyr — Bright & Crisp", "category": "Google AI Studio"},
        {"id": "Puck", "name": "Puck — Upbeat & Energetic", "category": "Google AI Studio"},
        {"id": "Charon", "name": "Charon — Informative & Deep", "category": "Google AI Studio"},
        {"id": "Kore", "name": "Kore — Firm & Focused", "category": "Google AI Studio"},
        {"id": "Fenrir", "name": "Fenrir — Bold & Energetic", "category": "Google AI Studio"},
        {"id": "Leda", "name": "Leda — Youthful & Clear", "category": "Google AI Studio"},
        {"id": "Orus", "name": "Orus — Firm & Steady", "category": "Google AI Studio"},
        {"id": "Aoede", "name": "Aoede — Breezy & Melodic", "category": "Google AI Studio"},
        {"id": "Callirrhoe", "name": "Callirrhoe — Easy-going & Natural", "category": "Google AI Studio"},
        {"id": "Autonoe", "name": "Autonoe — Bright & Articulate", "category": "Google AI Studio"},
        {"id": "Enceladus", "name": "Enceladus — Breathy & Soft", "category": "Google AI Studio"},
        {"id": "Iapetus", "name": "Iapetus — Clear & Direct", "category": "Google AI Studio"},
        {"id": "Umbriel", "name": "Umbriel — Easy-going & Smooth", "category": "Google AI Studio"},
        {"id": "Algieba", "name": "Algieba — Smooth & Balanced", "category": "Google AI Studio"},
        {"id": "Despina", "name": "Despina — Smooth & Warm", "category": "Google AI Studio"},
        {"id": "Erinome", "name": "Erinome — Clear & Precise", "category": "Google AI Studio"},
        {"id": "Algenib", "name": "Algenib — Gravelly & Distinct", "category": "Google AI Studio"},
        {"id": "Rasalgethi", "name": "Rasalgethi — Informative & Narrative", "category": "Google AI Studio"},
        {"id": "Laomedeia", "name": "Laomedeia — Upbeat & Lively", "category": "Google AI Studio"},
        {"id": "Achernar", "name": "Achernar — Soft & Gentle", "category": "Google AI Studio"},
        {"id": "Alnilam", "name": "Alnilam — Firm & Confident", "category": "Google AI Studio"},
        {"id": "Schedar", "name": "Schedar — Even & Composed", "category": "Google AI Studio"},
        {"id": "Gacrux", "name": "Gacrux — Mature & Rich", "category": "Google AI Studio"},
        {"id": "Pulcherrima", "name": "Pulcherrima — Forward & Bright", "category": "Google AI Studio"},
        {"id": "Achird", "name": "Achird — Friendly & Conversational", "category": "Google AI Studio"},
        {"id": "Zubenelgenubi", "name": "Zubenelgenubi — Casual & Relaxed", "category": "Google AI Studio"},
        {"id": "Vindemiatrix", "name": "Vindemiatrix — Gentle & Calm", "category": "Google AI Studio"},
        {"id": "Sadachbia", "name": "Sadachbia — Lively & Expressive", "category": "Google AI Studio"},
        {"id": "Sadaltager", "name": "Sadaltager — Knowledgeable & Clear", "category": "Google AI Studio"},
        {"id": "Sulafat", "name": "Sulafat — Warm & Inviting", "category": "Google AI Studio"},
        {"id": "Orpheus", "name": "Orpheus — Engaging & Narrative", "category": "Google AI Studio"},
        {"id": "Pegasus", "name": "Pegasus — Lively & Articulate", "category": "Google AI Studio"},
        {"id": "alloy", "name": "alloy (OpenAI alias)", "category": "Native Aliases"},
        {"id": "ash", "name": "ash (OpenAI alias)", "category": "Native Aliases"},
        {"id": "ballad", "name": "ballad (OpenAI alias)", "category": "Native Aliases"},
        {"id": "coral", "name": "coral (OpenAI alias)", "category": "Native Aliases"},
        {"id": "echo", "name": "echo (OpenAI alias)", "category": "Native Aliases"},
        {"id": "fable", "name": "fable (OpenAI alias)", "category": "Native Aliases"},
        {"id": "nova", "name": "nova (OpenAI alias)", "category": "Native Aliases"},
        {"id": "onyx", "name": "onyx (OpenAI alias)", "category": "Native Aliases"},
        {"id": "sage", "name": "sage (OpenAI alias)", "category": "Native Aliases"},
        {"id": "shimmer", "name": "shimmer (OpenAI alias)", "category": "Native Aliases"},
        {"id": "verse", "name": "verse (OpenAI alias)", "category": "Native Aliases"},
    ]

    def _merge(observed, baseline):
        seen = set()
        merged = []
        for o in observed:
            seen.add(o["id"])
            merged.append(o)
        for b in baseline:
            if b["id"] not in seen:
                seen.add(b["id"])
                merged.append({**b, "observed": False})
        return merged

    all_text = _merge(observed_text, baseline_text)
    all_image = _merge(observed_image, baseline_image)
    all_speech = _merge(observed_speech, baseline_speech)

    return {
        "config": EnvConfigManager.get_live_snapshot(),
        "catalog_observed": getattr(browser_manager, "model_catalog_observed", False),
        "models": {
            "text": all_text,
            "image": all_image,
            "speech": all_speech,
        },
        "voices": baseline_voices,
        "observed_models": [
            item["id"]
            for item in catalog.values()
            if item.get("status") == "selectable"
        ],
    }


@router.post("/api/dashboard/config")
async def update_dashboard_config(request: Request):
    """Save updated settings to .env on disk and hot-reload runtime configuration."""
    body = await request.json()
    if not isinstance(body, dict):
        raise GatewayError(400, "Expected JSON object of settings.", "invalid_request")
    updated = await asyncio.to_thread(EnvConfigManager.update_env_and_runtime, body)
    return {"status": "saved", "config": updated}


@router.post("/api/dashboard/engine/{action}")
async def control_browser_engine(action: str):
    """Start, stop, restart the Chromium engine, recycle idle tabs, or shut down the entire server."""
    owner = browser_manager._owner
    if action == "start":
        if owner.context and not getattr(owner, "context_closed", False) and not owner.is_shutting_down:
            return {"status": "already_running", "browser_ready": browser_manager.is_ready}
        asyncio.create_task(browser_manager.start())
        return {"status": "starting", "message": "Chromium engine is starting in the background."}

    if action == "stop":
        await browser_manager.stop()
        return {"status": "stopped", "message": "Chromium engine stopped; RAM freed."}

    if action == "restart":
        await browser_manager.stop()
        await asyncio.sleep(1.0)
        asyncio.create_task(browser_manager.start())
        return {"status": "restarting", "message": "Chromium engine is restarting with current settings."}

    if action in ("server_restart", "restart_server"):
        async def _restart_proc():
            await asyncio.sleep(0.5)
            try:
                await browser_manager.stop()
            finally:
                os.execv(sys.executable, [sys.executable, "app.py"])
        asyncio.create_task(_restart_proc())
        return {"status": "restarting", "message": "Python server process is restarting..."}

    if action == "recycle_tabs":
        await browser_manager.prune()
        return {"status": "recycled", "pool": browser_manager.stats()}

    if action == "refresh_catalog":
        if not owner or not owner.page or owner.page.is_closed():
            return {"status": "not_running", "message": "Chromium engine is currently stopped. Start the engine first to discover live cards."}
        try:
            await browser_manager.refresh_model_catalog()
            cnt = len(browser_manager.model_catalog)
            return {"status": "refreshed", "message": f"Discovered {cnt} selectable model cards from AI Studio.", "count": cnt}
        except Exception as e:
            return {"status": "error", "message": f"Catalog discovery failed: {e}"}

    if action == "shutdown_server":
        async def _exit_all():
            await asyncio.sleep(0.3)
            try:
                await browser_manager.stop()
            finally:
                os._exit(0)
        asyncio.create_task(_exit_all())
        return {"status": "shutting_down", "message": "Gateway and Dashboard server shutting down completely."}

    raise GatewayError(400, f"Unknown engine action: {action}", "invalid_request")


@router.post("/api/dashboard/accounts/{action}")
async def manage_dashboard_accounts(action: str, request: Request):
    """Switch active account, reset cooldowns, add account slot, or save session.json."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    if action == "reset_all":
        account_manager.reset_all_cooldowns()
        return {"status": "ok", "accounts": account_manager.stats()}

    if action == "reset_one":
        acc_id = body.get("account_id")
        if acc_id in account_manager.accounts:
            acc = account_manager.accounts[acc_id]
            acc.status = "ready"
            acc.limited_at = None
            acc.cooldown_until = None
            account_manager._save_state()
        return {"status": "ok", "accounts": account_manager.stats()}

    if action == "switch":
        acc_id = body.get("account_id")
        if acc_id not in account_manager.accounts:
            raise GatewayError(404, f"Account {acc_id} not found.", "account_not_found")
        target_acc = account_manager.accounts[acc_id]
        account_manager.active_id = target_acc.id
        target_acc.last_used_at = time.time()
        account_manager._save_state()
        if browser_manager._owner.page and not browser_manager._owner.page.is_closed():
            asyncio.create_task(browser_manager._owner.switch_account(target_acc))
        return {"status": "switching", "accounts": account_manager.stats()}

    if action == "add_slot":
        new_count = len(account_manager.accounts) + 1
        EnvConfigManager.update_env_and_runtime({"VIREL_GOOGLE_ACCOUNTS_COUNT": new_count})
        return {"status": "added", "accounts": account_manager.stats()}

    if action == "save_session":
        owner = browser_manager._owner
        page = owner.page if owner else None
        url = page.url if (page and not page.is_closed()) else config.TARGET_URL
        active_acc = account_manager.get_active_account()
        session_data = {
            "status": "ready",
            "profile_dir": os.path.abspath(config.CHROME_PROFILE_DIR),
            "created_at": int(time.time()),
            "url": url,
            "authuser": active_acc.authuser,
        }
        os.makedirs(os.path.dirname(os.path.abspath(config.SESSION_DATA_PATH)), exist_ok=True)
        with open(config.SESSION_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=4)
        if page and not page.is_closed() and "accounts.google.com" not in url:
            owner.needs_login = False
            owner.is_ready = True
        return {"status": "saved", "session": session_data}

    raise GatewayError(400, f"Unknown account action: {action}", "invalid_request")


@router.get("/api/dashboard/agents")
async def list_agent_keys():
    """Return all registered per-agent sub-keys and connection metadata."""
    base_url = config.PUBLIC_URL or f"http://localhost:{config.PORT}"
    return {
        "base_url": base_url,
        "local_url": f"http://localhost:{config.PORT}",
        "public_urls": config.PUBLIC_URLS,
        "default_model": config.DEFAULT_MODEL,
        "master_key_configured": bool(config.API_KEY),
        "keys": agent_keys.list_keys(),
    }


@router.post("/api/dashboard/agents/connect")
async def connect_agent_key(request: Request):
    """Generate or rotate a dedicated API key for a specific agent (Codex, Claude Code, Cline, Continue, OpenCode, n8n, MCP)."""
    body = await request.json()
    agent_id = body.get("agent_id", "agent")
    label = body.get("label", "")
    rotate = bool(body.get("rotate", False))
    record = agent_keys.create_or_rotate_key(agent_id, label=label, rotate=rotate)
    return {"status": "ok", "agent": record, "all_keys": agent_keys.list_keys()}


@router.delete("/api/dashboard/agents/{agent_id}")
async def revoke_agent_key_route(agent_id: str):
    agent_keys.revoke_key(agent_id)
    return {"status": "revoked", "all_keys": agent_keys.list_keys()}


@router.get("/api/dashboard/incidents")
async def get_incidents_list():
    """Return Blackbox incident screenshots organized by date and tab."""
    return {"incidents": await asyncio.to_thread(list_incidents, 60)}


@router.get("/api/dashboard/incidents/{date_str}/{filename}")
async def serve_incident_image(date_str: str, filename: str):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str) or not re.fullmatch(r"[A-Za-z0-9_.-]+\.png", filename):
        raise GatewayError(400, "Invalid incident path.", "invalid_request")
    target = os.path.join(config.RUNTIME_DIR, "incidents", date_str, filename)
    if not os.path.isfile(target):
        raise GatewayError(404, "Incident screenshot not found.", "not_found")
    return FileResponse(target, media_type="image/png")


@router.post("/api/dashboard/media/purge")
async def purge_or_enforce_media(request: Request):
    """Enforce 1GB media limit or clear all cached media files in runtime/."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    if body.get("clear_all"):
        for sub in ("generated_images", "generated_audio"):
            folder = Path(config.RUNTIME_DIR) / sub
            if folder.exists():
                for f in folder.iterdir():
                    if f.is_file():
                        f.unlink(missing_ok=True)
    result = await asyncio.to_thread(enforce_media_storage_limit)
    return {"status": "ok", "result": result, "media_storage": get_media_storage_stats()}


@router.get("/api/dashboard/backup/export")
async def export_gateway_snapshot():
    """Export .env settings, accounts_state.json, session.json, and agent_keys.json."""
    bundle = {
        "exported_at": int(time.time()),
        "env": EnvConfigManager.read_env_dict(),
        "agent_keys": agent_keys.keys,
        "accounts_state": {},
        "session": {},
    }
    if os.path.isfile(config.ACCOUNTS_STATE_PATH):
        try:
            with open(config.ACCOUNTS_STATE_PATH, "r", encoding="utf-8") as f:
                bundle["accounts_state"] = json.load(f)
        except Exception:
            pass
    if os.path.isfile(config.SESSION_DATA_PATH):
        try:
            with open(config.SESSION_DATA_PATH, "r", encoding="utf-8") as f:
                bundle["session"] = json.load(f)
        except Exception:
            pass
    return JSONResponse(bundle)


@router.post("/api/dashboard/backup/import")
async def import_gateway_snapshot(request: Request):
    """Restore .env settings, agent_keys.json, and session metadata from an exported bundle."""
    bundle = await request.json()
    if not isinstance(bundle, dict):
        raise GatewayError(400, "Invalid backup bundle.", "invalid_request")
    if isinstance(bundle.get("env"), dict):
        await asyncio.to_thread(EnvConfigManager.update_env_and_runtime, bundle["env"])
    if isinstance(bundle.get("agent_keys"), dict):
        agent_keys.keys = bundle["agent_keys"]
        agent_keys._save()
    if isinstance(bundle.get("session"), dict) and bundle["session"]:
        os.makedirs(os.path.dirname(os.path.abspath(config.SESSION_DATA_PATH)), exist_ok=True)
        with open(config.SESSION_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(bundle["session"], f, indent=2)
    return {"status": "restored", "config": EnvConfigManager.get_live_snapshot()}


@router.websocket("/ws/logs")
async def websocket_logs(ws: WebSocket):
    """Stream real-time server logs to the Dashboard terminal."""
    await ws.accept()
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    log_hub.subscribers.add(q)
    try:
        await ws.send_json({"type": "history", "logs": log_hub.recent(120)})
        while True:
            entry = await q.get()
            await ws.send_json({"type": "log", "entry": entry})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        log_hub.subscribers.discard(q)


def _resolve_omnibox_input(raw_input: str) -> str:
    """Convert search queries (e.g. 'speed test') into Google Search URLs, and domains into https:// URLs."""
    val = (raw_input or "").strip()
    if not val:
        return "https://www.google.com"
    if val.startswith(("http://", "https://", "about:")):
        return val
    # If it contains spaces or has no dot/localhost/port, treat as Google Search query
    if " " in val or ("." not in val and not val.startswith("localhost") and ":" not in val):
        return f"https://www.google.com/search?q={quote_plus(val)}"
    return "https://" + val


@router.websocket("/ws/browser")
async def websocket_live_browser(ws: WebSocket):
    """Zero-lag, frame-dropping 60 FPS CDP Screencast with direct CDP mouse/wheel/keyboard dispatch."""
    await ws.accept()
    active_tab_index: int = 0
    streaming = True
    cdp_session = None
    cdp_page = None
    sending_frame = False
    cached_dims = {"w": 1280, "h": 800}
    cached_tabs = []
    last_tabs_time = 0.0
    last_frame_ts = time.monotonic()

    def get_all_pages():
        owner = browser_manager._owner
        if not owner or not owner.context or getattr(owner, "context_closed", True) or owner.is_shutting_down:
            return []
        return [p for p in owner.context.pages if not p.is_closed()]

    def get_current_page():
        nonlocal active_tab_index
        pages = get_all_pages()
        if not pages:
            return None
        if active_tab_index < 0 or active_tab_index >= len(pages):
            active_tab_index = 0
        return pages[active_tab_index]

    def build_fast_tabs(pages):
        nonlocal cached_tabs, last_tabs_time
        now = time.monotonic()
        if now - last_tabs_time < 1.0 and len(cached_tabs) == len(pages):
            return cached_tabs
        last_tabs_time = now
        res = []
        for idx, p in enumerate(pages):
            u = p.url or "about:blank"
            label = u.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0] or f"Tab {idx + 1}"
            res.append({"index": idx, "title": label[:24], "url": u})
        cached_tabs = res
        return cached_tabs

    async def sync_dims(p):
        nonlocal cached_dims
        try:
            dims = await p.evaluate("() => ({ w: window.innerWidth, h: window.innerHeight })")
            if dims and dims.get("w") and dims.get("h"):
                cached_dims = {"w": int(dims["w"]), "h": int(dims["h"])}
        except Exception:
            pass

    async def push_frame(page, b64_data: str, w: int, h: int):
        nonlocal sending_frame, last_frame_ts
        if sending_frame or not streaming:
            return
        sending_frame = True
        try:
            pages = get_all_pages()
            await ws.send_json({
                "type": "frame",
                "image": b64_data,
                "url": page.url,
                "width": w,
                "height": h,
                "tabs": build_fast_tabs(pages),
                "active_index": active_tab_index,
            })
            last_frame_ts = time.monotonic()
        except Exception:
            pass
        finally:
            sending_frame = False

    async def attach_cdp(page):
        nonlocal cdp_session, cdp_page, cached_dims
        if cdp_page is page and cdp_session is not None:
            return
        if cdp_session is not None:
            try:
                await cdp_session.send("Page.stopScreencast")
                await cdp_session.detach()
            except Exception:
                pass
            cdp_session = None
            cdp_page = None

        try:
            await sync_dims(page)
            cdp_session = await page.context.new_cdp_session(page)
            cdp_page = page

            async def _handle_screencast(params):
                if not streaming or cdp_page is not page:
                    return
                sid = params.get("sessionId")
                if sid and cdp_session:
                    try:
                        await cdp_session.send("Page.screencastFrameAck", {"sessionId": sid})
                    except Exception:
                        pass
                if sending_frame:
                    return
                meta = params.get("metadata") or {}
                w = int(meta.get("deviceWidth") or cached_dims["w"] or 1280)
                h = int(meta.get("deviceHeight") or cached_dims["h"] or 800)
                cached_dims = {"w": w, "h": h}
                data = params.get("data")
                if data:
                    await push_frame(page, data, w, h)

            cdp_session.on("Page.screencastFrame", lambda p: asyncio.create_task(_handle_screencast(p)))
            await cdp_session.send("Page.startScreencast", {
                "format": "jpeg",
                "quality": 65,
                "maxWidth": 1280,
                "maxHeight": 780,
                "everyNthFrame": 1,
            })

            # Immediate initial frame via fast CDP captureScreenshot
            snap = await cdp_session.send("Page.captureScreenshot", {"format": "jpeg", "quality": 65})
            if snap and snap.get("data"):
                await push_frame(page, snap["data"], cached_dims["w"], cached_dims["h"])
        except Exception:
            cdp_session = None
            cdp_page = None

    async def watchdog_loop():
        nonlocal active_tab_index, cdp_session, cdp_page
        while streaming:
            try:
                pages = get_all_pages()
                if not pages:
                    cdp_session = None
                    cdp_page = None
                    await ws.send_json({
                        "type": "status",
                        "engine_running": False,
                        "message": "Chromium Engine is stopped. Click 'Start & Launch Chromium Now' below."
                    })
                    await asyncio.sleep(0.5)
                    continue

                if active_tab_index >= len(pages):
                    active_tab_index = max(0, len(pages) - 1)
                page = pages[active_tab_index]
                await attach_cdp(page)

                # Fallback snapshot only if screencast hasn't sent a frame in 0.65s (e.g. static background page)
                if cdp_session is not None and not sending_frame and (time.monotonic() - last_frame_ts) > 0.65:
                    try:
                        snap = await cdp_session.send("Page.captureScreenshot", {"format": "jpeg", "quality": 62})
                        if snap and snap.get("data"):
                            await push_frame(page, snap["data"], cached_dims["w"], cached_dims["h"])
                    except Exception:
                        pass
                await asyncio.sleep(0.25)
            except Exception:
                await asyncio.sleep(0.4)

    loop_task = asyncio.create_task(watchdog_loop())
    try:
        while True:
            raw = await ws.receive_text()
            cmd = json.loads(raw)
            action = cmd.get("action")

            if action == "start_engine":
                owner = browser_manager._owner
                if not owner.context or getattr(owner, "context_closed", False) or owner.is_shutting_down:
                    asyncio.create_task(browser_manager.start())
                continue

            pages = get_all_pages()
            if action == "new_tab":
                owner = browser_manager._owner
                if owner and owner.context and not getattr(owner, "context_closed", True):
                    new_p = await owner.context.new_page()
                    target_u = _resolve_omnibox_input(cmd.get("url") or "https://www.google.com")
                    asyncio.create_task(new_p.goto(target_u, timeout=45000, wait_until="domcontentloaded"))
                    pages = get_all_pages()
                    active_tab_index = max(0, len(pages) - 1)
                    last_tabs_time = 0.0
                    try:
                        await new_p.bring_to_front()
                    except Exception:
                        pass
                    await attach_cdp(new_p)
                continue

            if action == "switch_tab":
                idx = int(cmd.get("index", 0))
                if 0 <= idx < len(pages):
                    active_tab_index = idx
                    last_tabs_time = 0.0
                    target_p = pages[active_tab_index]
                    try:
                        await target_p.bring_to_front()
                    except Exception:
                        pass
                    await attach_cdp(target_p)
                continue

            if action == "close_tab":
                idx = int(cmd.get("index", active_tab_index))
                if len(pages) > 1 and 0 <= idx < len(pages):
                    try:
                        await pages[idx].close()
                    except Exception:
                        pass
                    pages = get_all_pages()
                    active_tab_index = min(active_tab_index, max(0, len(pages) - 1))
                    last_tabs_time = 0.0
                    if pages:
                        target_p = pages[active_tab_index]
                        try:
                            await target_p.bring_to_front()
                        except Exception:
                            pass
                        await attach_cdp(target_p)
                continue

            page = get_current_page()
            if not page or page.is_closed():
                continue

            # Dispatch inputs non-blockingly so mouse/keyboard never queue up
            if action == "click":
                x, y = float(cmd.get("x", 0)), float(cmd.get("y", 0))
                btn = cmd.get("button", "left")
                asyncio.create_task(page.mouse.click(x, y, button=btn))
            elif action == "mousedown":
                x, y = float(cmd.get("x", 0)), float(cmd.get("y", 0))
                btn = cmd.get("button", "left")
                if cdp_session:
                    asyncio.create_task(cdp_session.send("Input.dispatchMouseEvent", {
                        "type": "mousePressed", "x": x, "y": y, "button": btn, "clickCount": 1
                    }))
            elif action == "mouseup":
                x, y = float(cmd.get("x", 0)), float(cmd.get("y", 0))
                btn = cmd.get("button", "left")
                if cdp_session:
                    asyncio.create_task(cdp_session.send("Input.dispatchMouseEvent", {
                        "type": "mouseReleased", "x": x, "y": y, "button": btn, "clickCount": 1
                    }))
            elif action == "mousemove":
                x, y = float(cmd.get("x", 0)), float(cmd.get("y", 0))
                if cdp_session and not sending_frame:
                    asyncio.create_task(cdp_session.send("Input.dispatchMouseEvent", {
                        "type": "mouseMoved", "x": x, "y": y
                    }))
            elif action == "dblclick":
                x, y = float(cmd.get("x", 0)), float(cmd.get("y", 0))
                asyncio.create_task(page.mouse.dblclick(x, y))
            elif action == "wheel":
                dx, dy = float(cmd.get("deltaX", 0)), float(cmd.get("deltaY", 0))
                if cdp_session:
                    asyncio.create_task(cdp_session.send("Input.dispatchMouseEvent", {
                        "type": "mouseWheel", "x": 400, "y": 400, "deltaX": dx, "deltaY": dy
                    }))
                else:
                    asyncio.create_task(page.mouse.wheel(dx, dy))
            elif action == "type":
                text = cmd.get("text", "")
                if text:
                    if cdp_session:
                        asyncio.create_task(cdp_session.send("Input.insertText", {"text": text}))
                    else:
                        asyncio.create_task(page.keyboard.insert_text(text))
            elif action == "press":
                asyncio.create_task(page.keyboard.press(cmd.get("key", "Enter")))
            elif action == "goto":
                target_u = _resolve_omnibox_input(cmd.get("url", ""))
                last_tabs_time = 0.0
                asyncio.create_task(page.goto(target_u, timeout=45000, wait_until="domcontentloaded"))
            elif action == "back":
                last_tabs_time = 0.0
                asyncio.create_task(page.go_back(timeout=15000, wait_until="domcontentloaded"))
            elif action == "forward":
                last_tabs_time = 0.0
                asyncio.create_task(page.go_forward(timeout=15000, wait_until="domcontentloaded"))
            elif action == "reload":
                last_tabs_time = 0.0
                asyncio.create_task(page.reload(timeout=30000, wait_until="domcontentloaded"))
            elif action == "authuser":
                idx = int(cmd.get("index", 0))
                target = f"{config.TARGET_URL}?authuser={idx}"
                last_tabs_time = 0.0
                asyncio.create_task(page.goto(target, timeout=45000, wait_until="domcontentloaded"))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        streaming = False
        loop_task.cancel()
        if cdp_session is not None:
            try:
                await cdp_session.send("Page.stopScreencast")
                await cdp_session.detach()
            except Exception:
                pass
