"""Telemetry, SQLite token analytics, multi-agent API keys, 2-way .env sync, media ring-buffer, and incident recorder."""

import asyncio
import datetime
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import threading
import time
from collections import deque
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from . import config

logger = logging.getLogger("virel.webhook")

CURRENT_AGENT: ContextVar[str] = ContextVar("virel_current_agent", default="default")

TELEMETRY_DB_PATH = os.path.join(config.RUNTIME_DIR, "telemetry.db")
AGENT_KEYS_PATH = os.path.join(config.RUNTIME_DIR, "agent_keys.json")
INCIDENTS_DIR = os.path.join(config.RUNTIME_DIR, "incidents")
ENV_FILE_PATH = os.path.join(config.BASE_DIR, ".env")


class LogBroadcaster(logging.Handler):
    """Captures server logs in a ring buffer and broadcasts live to WebSocket subscribers."""
    def __init__(self, maxlen: int = 400):
        super().__init__()
        self.buffer: deque = deque(maxlen=maxlen)
        self.subscribers: set = set()
        self.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            entry = {
                "ts": int(time.time() * 1000),
                "time": datetime.datetime.now().strftime("%H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                "message": msg,
            }
            self.buffer.append(entry)
            if self.subscribers:
                dead = set()
                for q in list(self.subscribers):
                    try:
                        q.put_nowait(entry)
                    except Exception:
                        dead.add(q)
                self.subscribers -= dead
        except Exception:
            pass

    def recent(self, limit: int = 150) -> List[dict]:
        items = list(self.buffer)
        return items[-limit:]


log_hub = LogBroadcaster()
logging.getLogger("virel.webhook").addHandler(log_hub)
logging.getLogger("uvicorn.access").addHandler(log_hub)


class AgentKeyManager:
    """Manages per-agent API keys (Codex, Claude Code, Cline, Continue, OpenCode, n8n, MCP) alongside master VIREL_API_KEY."""
    def __init__(self, path: str = AGENT_KEYS_PATH):
        self.path = path
        self.lock = threading.RLock()
        self.keys: Dict[str, dict] = {}
        self._load()

    def _load(self):
        with self.lock:
            if not os.path.isfile(self.path):
                self.keys = {}
                return
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.keys = data
            except Exception as e:
                logger.warning("Could not load agent_keys.json: %s", e)
                self.keys = {}

    def _save(self):
        with self.lock:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.keys, f, indent=2)
                os.replace(tmp, self.path)
            except Exception as e:
                logger.warning("Could not save agent_keys.json: %s", e)

    def create_or_rotate_key(self, agent_id: str, label: str = "", rotate: bool = False) -> dict:
        clean_id = re.sub(r"[^a-z0-9_-]", "", agent_id.lower().strip())[:32] or "agent"
        with self.lock:
            if clean_id in self.keys and not rotate:
                return self.keys[clean_id]
            new_key = f"virel-{clean_id}-{secrets.token_hex(16)}"
            record = {
                "agent_id": clean_id,
                "label": label or clean_id.replace("_", " ").title(),
                "api_key": new_key,
                "created_at": int(time.time()),
            }
            self.keys[clean_id] = record
            self._save()
            return record

    def revoke_key(self, agent_id: str) -> bool:
        clean_id = agent_id.lower().strip()
        with self.lock:
            if clean_id in self.keys:
                del self.keys[clean_id]
                self._save()
                return True
            return False

    def list_keys(self) -> List[dict]:
        with self.lock:
            return list(self.keys.values())

    def verify_and_bind(self, token: Optional[str]) -> bool:
        """Return True if token is valid (master key or any registered agent sub-key) and bind CURRENT_AGENT."""
        master_raw = (config.API_KEY or "").strip()
        master_keys = [k.strip() for k in master_raw.split(",") if k.strip()]

        if not token:
            if not master_keys and not self.keys:
                CURRENT_AGENT.set("local")
                return True
            return False

        token = token.strip()
        with self.lock:
            for agent_id, info in self.keys.items():
                if info.get("api_key") and secrets.compare_digest(token, info["api_key"]):
                    CURRENT_AGENT.set(agent_id)
                    return True

        for mk in master_keys:
            if secrets.compare_digest(token, mk):
                # If token has virel-<agent>- prefix, extract agent name for analytics
                m = re.match(r"^virel-([a-z0-9_-]+)-[0-9a-f]{16,}$", token)
                CURRENT_AGENT.set(m.group(1) if m else "master")
                return True

        if not master_keys and not self.keys:
            CURRENT_AGENT.set("local")
            return True

        return False


agent_keys = AgentKeyManager()


class TelemetryStore:
    """Persistent SQLite analytics for per-account, per-agent, and time-series token telemetry."""
    def __init__(self, db_path: str = TELEMETRY_DB_PATH):
        self.db_path = db_path
        self.lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.lock:
            try:
                with self._connect() as conn:
                    conn.execute("PRAGMA journal_mode=WAL;")
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS request_logs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            request_id TEXT,
                            timestamp INTEGER NOT NULL,
                            date_str TEXT NOT NULL,
                            account_id TEXT NOT NULL,
                            account_label TEXT,
                            agent_id TEXT NOT NULL,
                            model TEXT NOT NULL,
                            kind TEXT NOT NULL,
                            input_tokens INTEGER NOT NULL DEFAULT 0,
                            output_tokens INTEGER NOT NULL DEFAULT 0,
                            reasoning_tokens INTEGER NOT NULL DEFAULT 0,
                            cached_tokens INTEGER NOT NULL DEFAULT 0,
                            total_tokens INTEGER NOT NULL DEFAULT 0,
                            latency_ms INTEGER NOT NULL DEFAULT 0,
                            tool_calls INTEGER NOT NULL DEFAULT 0,
                            status TEXT NOT NULL DEFAULT 'completed'
                        )
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_req_ts ON request_logs(timestamp);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_req_acc ON request_logs(account_id);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_req_agent ON request_logs(agent_id);")
            except Exception as e:
                logger.warning("Failed to initialize telemetry SQLite database: %s", e)

    def record_request(
        self,
        *,
        request_id: str,
        account_id: str,
        account_label: str = "",
        agent_id: Optional[str] = None,
        model: str = "",
        kind: str = "text",
        input_tokens: int = 0,
        output_tokens: int = 0,
        reasoning_tokens: int = 0,
        cached_tokens: int = 0,
        total_tokens: int = 0,
        latency_ms: int = 0,
        tool_calls: int = 0,
        status: str = "completed",
    ):
        now = int(time.time())
        date_str = datetime.datetime.fromtimestamp(now).strftime("%Y-%m-%d")
        resolved_agent = agent_id or CURRENT_AGENT.get() or "default"
        if not total_tokens and (input_tokens or output_tokens or reasoning_tokens):
            total_tokens = int(input_tokens or 0) + int(output_tokens or 0)

        with self.lock:
            try:
                with self._connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO request_logs (
                            request_id, timestamp, date_str, account_id, account_label,
                            agent_id, model, kind, input_tokens, output_tokens,
                            reasoning_tokens, cached_tokens, total_tokens, latency_ms,
                            tool_calls, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            request_id,
                            now,
                            date_str,
                            account_id or "authuser_0",
                            account_label or account_id or "authuser=0",
                            resolved_agent,
                            model or config.DEFAULT_MODEL,
                            kind,
                            int(input_tokens or 0),
                            int(output_tokens or 0),
                            int(reasoning_tokens or 0),
                            int(cached_tokens or 0),
                            int(total_tokens or 0),
                            int(latency_ms or 0),
                            int(tool_calls or 0),
                            status,
                        ),
                    )
            except Exception as e:
                logger.warning("Failed to record request telemetry: %s", e)

    @staticmethod
    def _period_cutoff(period: str) -> int:
        now = datetime.datetime.now()
        p = (period or "all").lower().strip()
        if p in ("today", "day", "24h"):
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return int(start.timestamp())
        if p in ("week", "7d"):
            start = (now - datetime.timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
            return int(start.timestamp())
        if p in ("month", "30d"):
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return int(start.timestamp())
        if p in ("year", "365d"):
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            return int(start.timestamp())
        return 0

    def query_analytics(self, period: str = "all") -> dict:
        cutoff = self._period_cutoff(period)
        with self.lock:
            try:
                with self._connect() as conn:
                    # 1. Combined summary for period
                    row = conn.execute(
                        """
                        SELECT
                            COUNT(*) AS total_requests,
                            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_requests,
                            SUM(CASE WHEN status != 'completed' THEN 1 ELSE 0 END) AS failed_requests,
                            COALESCE(SUM(input_tokens), 0) AS input_tokens,
                            COALESCE(SUM(output_tokens), 0) AS output_tokens,
                            COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
                            COALESCE(SUM(cached_tokens), 0) AS cached_tokens,
                            COALESCE(SUM(total_tokens), 0) AS total_tokens,
                            COALESCE(AVG(NULLIF(latency_ms, 0)), 0) AS avg_latency_ms,
                            COALESCE(SUM(tool_calls), 0) AS total_tool_calls,
                            SUM(CASE WHEN kind = 'image' AND status = 'completed' THEN 1 ELSE 0 END) AS images_generated,
                            SUM(CASE WHEN kind = 'speech' AND status = 'completed' THEN 1 ELSE 0 END) AS audio_generated
                        FROM request_logs
                        WHERE timestamp >= ?
                        """,
                        (cutoff,),
                    ).fetchone()

                    summary = dict(row) if row else {}
                    for k in ("completed_requests", "failed_requests", "images_generated", "audio_generated"):
                        summary[k] = int(summary.get(k) or 0)
                    summary["avg_latency_ms"] = int(round(summary.get("avg_latency_ms") or 0))

                    # Estimate API cost saved ($1.25 / 1M input + $5.00 / 1M output + $0.04/image + $0.015/audio)
                    saved_usd = (
                        (summary.get("input_tokens", 0) / 1_000_000.0) * 1.25
                        + (summary.get("output_tokens", 0) / 1_000_000.0) * 5.00
                        + summary.get("images_generated", 0) * 0.04
                        + summary.get("audio_generated", 0) * 0.015
                    )
                    summary["estimated_cost_saved_usd"] = round(saved_usd, 4)

                    # 2. Per-Account breakdown for selected period
                    acc_rows = conn.execute(
                        """
                        SELECT
                            account_id,
                            MAX(account_label) AS account_label,
                            COUNT(*) AS requests,
                            COALESCE(SUM(input_tokens), 0) AS input_tokens,
                            COALESCE(SUM(output_tokens), 0) AS output_tokens,
                            COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
                            COALESCE(SUM(total_tokens), 0) AS total_tokens,
                            COALESCE(AVG(NULLIF(latency_ms, 0)), 0) AS avg_latency_ms
                        FROM request_logs
                        WHERE timestamp >= ?
                        GROUP BY account_id
                        ORDER BY total_tokens DESC
                        """,
                        (cutoff,),
                    ).fetchall()

                    # Also fetch all-time totals per account so user always sees lifetime + period
                    all_acc_rows = conn.execute(
                        """
                        SELECT
                            account_id,
                            COUNT(*) AS all_time_requests,
                            COALESCE(SUM(total_tokens), 0) AS all_time_tokens
                        FROM request_logs
                        GROUP BY account_id
                        """
                    ).fetchall()
                    all_time_map = {r["account_id"]: dict(r) for r in all_acc_rows}

                    per_account = []
                    for r in acc_rows:
                        d = dict(r)
                        d["avg_latency_ms"] = int(round(d.get("avg_latency_ms") or 0))
                        at = all_time_map.get(d["account_id"], {})
                        d["all_time_requests"] = at.get("all_time_requests", d["requests"])
                        d["all_time_tokens"] = at.get("all_time_tokens", d["total_tokens"])
                        per_account.append(d)

                    # 3. Per-Agent breakdown
                    agent_rows = conn.execute(
                        """
                        SELECT
                            agent_id,
                            COUNT(*) AS requests,
                            COALESCE(SUM(input_tokens), 0) AS input_tokens,
                            COALESCE(SUM(output_tokens), 0) AS output_tokens,
                            COALESCE(SUM(total_tokens), 0) AS total_tokens
                        FROM request_logs
                        WHERE timestamp >= ?
                        GROUP BY agent_id
                        ORDER BY total_tokens DESC
                        """,
                        (cutoff,),
                    ).fetchall()
                    per_agent = [dict(r) for r in agent_rows]

                    # 4. Per-Model breakdown
                    model_rows = conn.execute(
                        """
                        SELECT
                            model,
                            COUNT(*) AS requests,
                            COALESCE(SUM(total_tokens), 0) AS total_tokens
                        FROM request_logs
                        WHERE timestamp >= ?
                        GROUP BY model
                        ORDER BY total_tokens DESC
                        """,
                        (cutoff,),
                    ).fetchall()
                    per_model = [dict(r) for r in model_rows]

                    # 5. Timeline series for charts
                    if (period or "").lower() in ("today", "day", "24h"):
                        ts_rows = conn.execute(
                            """
                            SELECT
                                strftime('%H:00', datetime(timestamp, 'unixepoch', 'localtime')) AS bucket,
                                COUNT(*) AS requests,
                                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                                COALESCE(SUM(total_tokens), 0) AS total_tokens
                            FROM request_logs
                            WHERE timestamp >= ?
                            GROUP BY bucket
                            ORDER BY bucket ASC
                            """,
                            (cutoff,),
                        ).fetchall()
                    else:
                        ts_rows = conn.execute(
                            """
                            SELECT
                                date_str AS bucket,
                                COUNT(*) AS requests,
                                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                                COALESCE(SUM(total_tokens), 0) AS total_tokens
                            FROM request_logs
                            WHERE timestamp >= ?
                            GROUP BY bucket
                            ORDER BY bucket ASC
                            LIMIT 60
                            """,
                            (cutoff,),
                        ).fetchall()
                    timeline = [dict(r) for r in ts_rows]

                    # 6. Quick summary across all 5 standard windows (Today, Week, Month, Year, All-Time)
                    windows = {}
                    for w_name in ("today", "week", "month", "year", "all"):
                        w_cut = self._period_cutoff(w_name)
                        w_row = conn.execute(
                            """
                            SELECT
                                COUNT(*) AS requests,
                                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                                COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
                                COALESCE(SUM(total_tokens), 0) AS total_tokens
                            FROM request_logs
                            WHERE timestamp >= ?
                            """,
                            (w_cut,),
                        ).fetchone()
                        windows[w_name] = dict(w_row) if w_row else {}

                    # 7. Recent 40 request traces
                    trace_rows = conn.execute(
                        """
                        SELECT
                            id, request_id, timestamp, account_id, agent_id, model, kind,
                            input_tokens, output_tokens, reasoning_tokens, total_tokens,
                            latency_ms, tool_calls, status
                        FROM request_logs
                        ORDER BY id DESC
                        LIMIT 40
                        """
                    ).fetchall()
                    recent_traces = [dict(r) for r in trace_rows]

                    return {
                        "period": period,
                        "summary": summary,
                        "windows": windows,
                        "per_account": per_account,
                        "per_agent": per_agent,
                        "per_model": per_model,
                        "timeline": timeline,
                        "recent_traces": recent_traces,
                    }
            except Exception as e:
                logger.warning("Analytics query failed: %s", e)
                return {
                    "period": period,
                    "summary": {},
                    "windows": {},
                    "per_account": [],
                    "per_agent": [],
                    "per_model": [],
                    "timeline": [],
                    "recent_traces": [],
                }


store = TelemetryStore()


async def capture_incident_screenshot(page, tab_id: str, reason: str = "error") -> Optional[str]:
    """Capture a Blackbox incident screenshot organized by date folder (YYYY-MM-DD/tab_<id>_HH-MM-SS_<reason>.png)."""
    if not page or page.is_closed():
        return None
    try:
        now = datetime.datetime.now()
        date_folder = now.strftime("%Y-%m-%d")
        time_stamp = now.strftime("%H-%M-%S")
        clean_reason = re.sub(r"[^a-zA-Z0-9_-]", "_", (reason or "error"))[:32]
        clean_tab = re.sub(r"[^a-zA-Z0-9_-]", "", str(tab_id or "main"))[:16]
        day_dir = Path(INCIDENTS_DIR) / date_folder
        day_dir.mkdir(parents=True, exist_ok=True)
        fname = f"tab_{clean_tab}_{time_stamp}_{clean_reason}.png"
        full_path = day_dir / fname
        await page.screenshot(path=str(full_path), timeout=4000)
        logger.info("Blackbox incident screenshot saved: %s/%s", date_folder, fname)
        return f"{date_folder}/{fname}"
    except Exception as e:
        logger.debug("Could not capture incident screenshot: %s", e)
        return None


def list_incidents(limit: int = 50) -> List[dict]:
    """Return recorded incident screenshots grouped with date, time, and tab metadata."""
    root = Path(INCIDENTS_DIR)
    if not root.exists():
        return []
    items = []
    for day_dir in sorted(root.iterdir(), reverse=True):
        if not day_dir.is_dir():
            continue
        for img in sorted(day_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True):
            stat = img.stat()
            items.append({
                "date": day_dir.name,
                "filename": img.name,
                "rel_path": f"{day_dir.name}/{img.name}",
                "url": f"/api/dashboard/incidents/{day_dir.name}/{img.name}",
                "size_kb": round(stat.st_size / 1024.0, 1),
                "created_at": int(stat.st_mtime),
            })
            if len(items) >= limit:
                return items
    return items


def get_media_storage_stats() -> dict:
    """Measure runtime/generated_images and runtime/generated_audio usage and enforce limits."""
    img_dir = Path(config.RUNTIME_DIR) / "generated_images"
    aud_dir = Path(config.RUNTIME_DIR) / "generated_audio"
    files_list = []
    total_bytes = 0
    for kind, folder in (("image", img_dir), ("audio", aud_dir)):
        if folder.exists():
            for f in folder.iterdir():
                if f.is_file():
                    sz = f.stat().st_size
                    total_bytes += sz
                    files_list.append({
                        "kind": kind,
                        "name": f.name,
                        "path": str(f),
                        "url": f"/images/{f.name}" if kind == "image" else f"/audio/{f.name}",
                        "bytes": sz,
                        "mtime": int(f.stat().st_mtime),
                    })
    files_list.sort(key=lambda x: x["mtime"], reverse=True)
    max_mb = int(os.getenv("VIREL_MEDIA_CACHE_MAX_MB", "1024"))
    return {
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "max_mb": max_mb,
        "file_count": len(files_list),
        "offload_dir": os.getenv("VIREL_MEDIA_OFFLOAD_DIR", "").strip(),
        "recent_files": files_list[:24],
    }


def enforce_media_storage_limit() -> dict:
    """If generated media cache exceeds VIREL_MEDIA_CACHE_MAX_MB (default 1024 MB = 1 GB), offload to Drive/Archive folder or evict oldest."""
    max_mb = int(os.getenv("VIREL_MEDIA_CACHE_MAX_MB", "1024"))
    max_bytes = max(10, max_mb) * 1024 * 1024
    offload_dir = os.getenv("VIREL_MEDIA_OFFLOAD_DIR", "").strip()

    img_dir = Path(config.RUNTIME_DIR) / "generated_images"
    aud_dir = Path(config.RUNTIME_DIR) / "generated_audio"
    all_files = []
    total_bytes = 0
    for folder in (img_dir, aud_dir):
        if folder.exists():
            for f in folder.iterdir():
                if f.is_file():
                    st = f.stat()
                    total_bytes += st.st_size
                    all_files.append((st.st_mtime, st.st_size, f))

    evicted = 0
    offloaded = 0
    if total_bytes > max_bytes:
        # Sort oldest first
        all_files.sort(key=lambda x: x[0])
        target_bytes = int(max_bytes * 0.75)
        day_str = datetime.datetime.now().strftime("%Y-%m-%d")
        for _, sz, fpath in all_files:
            if total_bytes <= target_bytes:
                break
            try:
                if offload_dir:
                    dest_folder = Path(offload_dir) / day_str
                    dest_folder.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(fpath), str(dest_folder / fpath.name))
                    offloaded += 1
                else:
                    fpath.unlink(missing_ok=True)
                    evicted += 1
                total_bytes -= sz
            except Exception as e:
                logger.warning("Media cache cleanup failed for %s: %s", fpath.name, e)

    return {"total_mb": round(total_bytes / (1024 * 1024), 2), "max_mb": max_mb, "evicted": evicted, "offloaded": offloaded}


class EnvConfigManager:
    """Two-way .env configuration reader and live runtime updater."""
    MANAGED_KEYS = [
        "VIREL_API_KEY",
        "PORT",
        "VIREL_PUBLIC_URL",
        "HEADLESS",
        "CHROME_PROFILE_DIR",
        "DEFAULT_MODEL",
        "DEFAULT_IMAGE_MODEL",
        "DEFAULT_SPEECH_MODEL",
        "DEFAULT_SPEECH_VOICE",
        "THINKING_MODE",
        "ENABLE_URL_CONTEXT",
        "ENABLE_SEARCH_GROUNDING",
        "VIREL_ENABLE_SERVER_TOOLS",
        "VIREL_PRESERVE_MARKDOWN",
        "VIREL_GOOGLE_ACCOUNTS_COUNT",
        "VIREL_ACCOUNT_COOLDOWN_HOURS",
        "VIREL_LOAD_BALANCE_MODE",
        "VIREL_MAX_CONCURRENT",
        "VIREL_MAX_QUEUE",
        "VIREL_QUEUE_TIMEOUT_SECONDS",
        "VIREL_MEMORY_RESERVE_MB",
        "VIREL_TAB_MEMORY_MB",
        "VIREL_MAX_WAITING_TABS",
        "VIREL_TOOL_RUN_TTL_SECONDS",
        "VIREL_RATE_LIMIT",
        "VIREL_MEDIA_CACHE_MAX_MB",
        "VIREL_MEDIA_OFFLOAD_DIR",
    ]

    @classmethod
    def read_env_dict(cls) -> Dict[str, str]:
        values: Dict[str, str] = {}
        if os.path.isfile(ENV_FILE_PATH):
            try:
                with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
                    for line in f:
                        stripped = line.strip()
                        if not stripped or stripped.startswith("#") or "=" not in stripped:
                            continue
                        k, v = stripped.split("=", 1)
                        k = k.strip()
                        v = v.strip()
                        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                            v = v[1:-1]
                        values[k] = v
            except Exception as e:
                logger.warning("Failed reading .env: %s", e)
        return values

    @classmethod
    def get_live_snapshot(cls) -> dict:
        disk = cls.read_env_dict()
        from .runtime import account_manager, browser_manager
        public_urls = config.PUBLIC_URLS
        return {
            "VIREL_API_KEY": disk.get("VIREL_API_KEY", config.API_KEY),
            "PORT": int(disk.get("PORT", config.PORT)),
            "VIREL_PUBLIC_URL": disk.get("VIREL_PUBLIC_URL", ",".join(public_urls)),
            "PUBLIC_URLS_LIST": public_urls,
            "HEADLESS": disk.get("HEADLESS", str(config.HEADLESS).lower()).lower() in ("true", "1", "yes"),
            "CHROME_PROFILE_DIR": disk.get("CHROME_PROFILE_DIR", config.CHROME_PROFILE_DIR),
            "DEFAULT_MODEL": disk.get("DEFAULT_MODEL", config.DEFAULT_MODEL),
            "DEFAULT_IMAGE_MODEL": disk.get("DEFAULT_IMAGE_MODEL", config.DEFAULT_IMAGE_MODEL),
            "DEFAULT_SPEECH_MODEL": disk.get("DEFAULT_SPEECH_MODEL", config.DEFAULT_SPEECH_MODEL),
            "DEFAULT_SPEECH_VOICE": disk.get("DEFAULT_SPEECH_VOICE", config.DEFAULT_SPEECH_VOICE),
            "THINKING_MODE": disk.get("THINKING_MODE", config.THINKING_MODE),
            "ENABLE_URL_CONTEXT": disk.get("ENABLE_URL_CONTEXT", str(config.ENABLE_URL_CONTEXT).lower()).lower() in ("true", "1", "yes"),
            "ENABLE_SEARCH_GROUNDING": disk.get("ENABLE_SEARCH_GROUNDING", str(config.ENABLE_SEARCH_GROUNDING).lower()).lower() in ("true", "1", "yes"),
            "VIREL_ENABLE_SERVER_TOOLS": disk.get("VIREL_ENABLE_SERVER_TOOLS", str(config.ENABLE_SERVER_TOOLS).lower()).lower() in ("true", "1", "yes"),
            "VIREL_PRESERVE_MARKDOWN": disk.get("VIREL_PRESERVE_MARKDOWN", str(config.PRESERVE_MARKDOWN).lower()).lower() in ("true", "1", "yes"),
            "VIREL_GOOGLE_ACCOUNTS_COUNT": int(disk.get("VIREL_GOOGLE_ACCOUNTS_COUNT", account_manager.authuser_count)),
            "VIREL_ACCOUNT_COOLDOWN_HOURS": float(disk.get("VIREL_ACCOUNT_COOLDOWN_HOURS", config.VIREL_ACCOUNT_COOLDOWN_HOURS)),
            "VIREL_LOAD_BALANCE_MODE": disk.get("VIREL_LOAD_BALANCE_MODE", getattr(account_manager, "load_balance_mode", "failover")),
            "VIREL_MAX_CONCURRENT": int(disk.get("VIREL_MAX_CONCURRENT", browser_manager.max_active)),
            "VIREL_MAX_QUEUE": int(disk.get("VIREL_MAX_QUEUE", browser_manager.max_queue)),
            "VIREL_QUEUE_TIMEOUT_SECONDS": int(disk.get("VIREL_QUEUE_TIMEOUT_SECONDS", browser_manager.timeout)),
            "VIREL_MEMORY_RESERVE_MB": int(disk.get("VIREL_MEMORY_RESERVE_MB", browser_manager.reserve // (1024 * 1024))),
            "VIREL_TAB_MEMORY_MB": int(disk.get("VIREL_TAB_MEMORY_MB", browser_manager.tab_bytes // (1024 * 1024))),
            "VIREL_MAX_WAITING_TABS": int(disk.get("VIREL_MAX_WAITING_TABS", browser_manager.max_waiting)),
            "VIREL_TOOL_RUN_TTL_SECONDS": int(disk.get("VIREL_TOOL_RUN_TTL_SECONDS", config.TOOL_RUN_TTL_SECONDS)),
            "VIREL_RATE_LIMIT": disk.get("VIREL_RATE_LIMIT", config.RATE_LIMIT),
            "VIREL_MEDIA_CACHE_MAX_MB": int(disk.get("VIREL_MEDIA_CACHE_MAX_MB", os.getenv("VIREL_MEDIA_CACHE_MAX_MB", "1024"))),
            "VIREL_MEDIA_OFFLOAD_DIR": disk.get("VIREL_MEDIA_OFFLOAD_DIR", os.getenv("VIREL_MEDIA_OFFLOAD_DIR", "")),
        }

    @classmethod
    def update_env_and_runtime(cls, updates: Dict[str, Any]) -> dict:
        """Write updates to .env preserving comments/structure AND hot-reload live runtime objects."""
        clean_updates: Dict[str, str] = {}
        for k, v in updates.items():
            if k not in cls.MANAGED_KEYS:
                continue
            if isinstance(v, bool):
                clean_updates[k] = "true" if v else "false"
            elif isinstance(v, list):
                clean_updates[k] = ",".join(str(x).strip() for x in v if str(x).strip())
            elif v is None:
                clean_updates[k] = ""
            else:
                clean_updates[k] = str(v).strip()

        # 1. Persist to .env file
        lines: List[str] = []
        if os.path.isfile(ENV_FILE_PATH):
            with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()

        written_keys = set()
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in clean_updates:
                    new_lines.append(f"{key}={clean_updates[key]}\n")
                    written_keys.add(key)
                    continue
            new_lines.append(line)

        for key, val in clean_updates.items():
            if key not in written_keys:
                if new_lines and not new_lines[-1].endswith("\n"):
                    new_lines[-1] += "\n"
                new_lines.append(f"{key}={val}\n")

        tmp_env = ENV_FILE_PATH + ".tmp"
        with open(tmp_env, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        os.replace(tmp_env, ENV_FILE_PATH)

        # 2. Hot-update os.environ & virel.config & live runtime managers
        for key, val in clean_updates.items():
            os.environ[key] = val

        from . import auth
        from .runtime import account_manager, browser_manager

        if "VIREL_API_KEY" in clean_updates:
            config.API_KEY = clean_updates["VIREL_API_KEY"]
            auth.API_KEY = clean_updates["VIREL_API_KEY"]

        if "VIREL_PUBLIC_URL" in clean_updates:
            raw_pub = clean_updates["VIREL_PUBLIC_URL"]
            pub_list = [config._normalize_public_url(u) for u in raw_pub.split(",") if config._normalize_public_url(u)]
            config.PUBLIC_URLS.clear()
            config.PUBLIC_URLS.extend(pub_list)
            config.PUBLIC_URL = pub_list[0] if pub_list else ""
            config.ALLOWED_PUBLIC_HOSTS.clear()
            for u in pub_list:
                hn = (urlsplit(u).hostname or "").lower()
                if hn:
                    config.ALLOWED_PUBLIC_HOSTS[hn] = u

        if "HEADLESS" in clean_updates:
            config.HEADLESS = clean_updates["HEADLESS"].lower() in ("true", "1", "yes")
        if "DEFAULT_MODEL" in clean_updates and clean_updates["DEFAULT_MODEL"]:
            config.DEFAULT_MODEL = clean_updates["DEFAULT_MODEL"]
        if "DEFAULT_IMAGE_MODEL" in clean_updates and clean_updates["DEFAULT_IMAGE_MODEL"]:
            config.DEFAULT_IMAGE_MODEL = clean_updates["DEFAULT_IMAGE_MODEL"]
        if "DEFAULT_SPEECH_MODEL" in clean_updates and clean_updates["DEFAULT_SPEECH_MODEL"]:
            config.DEFAULT_SPEECH_MODEL = clean_updates["DEFAULT_SPEECH_MODEL"]
        if "DEFAULT_SPEECH_VOICE" in clean_updates and clean_updates["DEFAULT_SPEECH_VOICE"]:
            config.DEFAULT_SPEECH_VOICE = clean_updates["DEFAULT_SPEECH_VOICE"]
        if "THINKING_MODE" in clean_updates and clean_updates["THINKING_MODE"]:
            config.THINKING_MODE = clean_updates["THINKING_MODE"].lower()
        if "ENABLE_URL_CONTEXT" in clean_updates:
            config.ENABLE_URL_CONTEXT = clean_updates["ENABLE_URL_CONTEXT"].lower() in ("true", "1", "yes")
        if "ENABLE_SEARCH_GROUNDING" in clean_updates:
            config.ENABLE_SEARCH_GROUNDING = clean_updates["ENABLE_SEARCH_GROUNDING"].lower() in ("true", "1", "yes")
        if "VIREL_ENABLE_SERVER_TOOLS" in clean_updates:
            config.ENABLE_SERVER_TOOLS = clean_updates["VIREL_ENABLE_SERVER_TOOLS"].lower() in ("true", "1", "yes")
        if "VIREL_PRESERVE_MARKDOWN" in clean_updates:
            config.PRESERVE_MARKDOWN = clean_updates["VIREL_PRESERVE_MARKDOWN"].lower() in ("true", "1", "yes")

        if "VIREL_ACCOUNT_COOLDOWN_HOURS" in clean_updates:
            hrs = max(0.05, float(clean_updates["VIREL_ACCOUNT_COOLDOWN_HOURS"]))
            config.VIREL_ACCOUNT_COOLDOWN_HOURS = hrs
            config.VIREL_ACCOUNT_COOLDOWN_SECONDS = max(60.0, hrs * 3600)
            account_manager.cooldown_seconds = config.VIREL_ACCOUNT_COOLDOWN_SECONDS
            for acc in account_manager.accounts.values():
                acc.cooldown_seconds = config.VIREL_ACCOUNT_COOLDOWN_SECONDS

        if "VIREL_GOOGLE_ACCOUNTS_COUNT" in clean_updates:
            cnt = max(1, int(clean_updates["VIREL_GOOGLE_ACCOUNTS_COUNT"]))
            config.VIREL_GOOGLE_ACCOUNTS_COUNT = cnt
            account_manager.authuser_count = cnt
            from .accounts import Account
            for i in range(cnt):
                acc_id = f"authuser_{i}"
                if acc_id not in account_manager.accounts:
                    account_manager.accounts[acc_id] = Account(
                        account_id=acc_id,
                        profile_dir=account_manager.default_profile_dir,
                        authuser=i,
                        cooldown_seconds=account_manager.cooldown_seconds,
                        label=f"authuser={i}",
                    )
            account_manager._save_state()

        if "VIREL_LOAD_BALANCE_MODE" in clean_updates:
            mode = clean_updates["VIREL_LOAD_BALANCE_MODE"].lower()
            if mode in ("failover", "round_robin"):
                account_manager.load_balance_mode = mode

        if "VIREL_MAX_CONCURRENT" in clean_updates:
            browser_manager.max_active = max(1, int(clean_updates["VIREL_MAX_CONCURRENT"]))
        if "VIREL_MAX_QUEUE" in clean_updates:
            browser_manager.max_queue = max(1, int(clean_updates["VIREL_MAX_QUEUE"]))
        if "VIREL_QUEUE_TIMEOUT_SECONDS" in clean_updates:
            browser_manager.timeout = max(5, int(clean_updates["VIREL_QUEUE_TIMEOUT_SECONDS"]))
        if "VIREL_MEMORY_RESERVE_MB" in clean_updates:
            browser_manager.reserve = max(128, int(clean_updates["VIREL_MEMORY_RESERVE_MB"])) * 1024 * 1024
        if "VIREL_TAB_MEMORY_MB" in clean_updates:
            browser_manager.tab_bytes = max(64, int(clean_updates["VIREL_TAB_MEMORY_MB"])) * 1024 * 1024
        if "VIREL_MAX_WAITING_TABS" in clean_updates:
            browser_manager.max_waiting = max(1, int(clean_updates["VIREL_MAX_WAITING_TABS"]))

        return cls.get_live_snapshot()
