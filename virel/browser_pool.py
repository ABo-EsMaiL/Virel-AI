"""One browser context, task-owned pages, and bounded RAM-aware admission."""
import asyncio
import time
import uuid
import logging
from contextvars import ContextVar
from contextlib import suppress
from types import SimpleNamespace
from pathlib import Path
from anyio import CancelScope
import psutil
from starlette.responses import JSONResponse
from .errors import GatewayError, provider_error
from .tool_runs import digest

logger = logging.getLogger("virel.webhook")
MB = 1024 * 1024
GENERATING = {"/v1/chat/completions", "/v1/responses", "/responses", "/v1/completions",
              "/v1/images/generations", "/v1/images/edits", "/v1/audio/transcriptions",
              "/v1/audio/translations", "/v1/audio/speech"}

def available_memory():
    available = psutil.virtual_memory().available
    for limit_path, usage_path in (
        ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
        ("/sys/fs/cgroup/memory/memory.limit_in_bytes", "/sys/fs/cgroup/memory/memory.usage_in_bytes"),
    ):
        try:
            limit, usage = int(Path(limit_path).read_text().strip()), int(Path(usage_path).read_text().strip())
            available = min(available, max(0, limit-usage))
        except (OSError, ValueError):
            pass
    return available

class BrowserPool:
    def __init__(self, owner, *, max_active, max_queue, timeout, reserve_mb, tab_mb, max_waiting, memory=None):
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_scope", ContextVar("virel_request", default=None))
        object.__setattr__(self, "_browser_fields", frozenset(dir(owner)))
        self.max_active, self.max_queue, self.timeout = max_active, max_queue, timeout
        self.reserve, self.tab_bytes, self.max_waiting = reserve_mb*MB, tab_mb*MB, max_waiting
        self.memory = memory or available_memory
        self.slots, self.queue, self.quarantined = {}, [], {}
        self.active = self.incoming = self.reserved_tools = 0
        self.condition = asyncio.Condition()
        self.closing = False

    @property
    def current(self):
        return self._scope.get()

    def __getattr__(self, name):
        scope = self.current
        return getattr(scope.worker if scope and scope.worker else self._owner, name)

    def __setattr__(self, name, value):
        if name in self._browser_fields:
            scope = self.current
            setattr(scope.worker if scope and scope.worker else self._owner, name, value)
        else:
            object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if name in self._browser_fields:
            scope = self.current
            delattr(scope.worker if scope and scope.worker else self._owner, name)
        else:
            object.__delattr__(self, name)

    def new_scope(self, owner="", needs_page=True):
        return SimpleNamespace(id=uuid.uuid4().hex, owner=digest(owner.split()[-1] if owner.split() else ""),
                               needs_page=needs_page, worker=None, history=None, tool_capable=False,
                               slot=None, original_pending=None, admitted=False, entered=False,
                               released=False, tool_reserved=False, status=500)

    async def enter(self, scope):
        async with self.condition:
            if self.closing:
                raise GatewayError(503, "Browser is shutting down.", "browser_not_ready")
            if self.incoming >= self.max_active + self.max_queue:
                raise GatewayError(429, "Request queue is full.", "request_queue_full")
            self.incoming += 1
            scope.entered = True

    def prepare(self, history, tool_capable=True):
        scope = self.current
        if scope is not None:
            scope.history, scope.tool_capable = history, tool_capable

    async def create_page(self):
        from .browser import BrowserPage
        if self.quarantined:
            raise GatewayError(503, "A browser page is still being cleaned up.", "browser_cleanup_pending")
        if not self._owner.context or self._owner.is_shutting_down:
            raise GatewayError(503, "Browser context is unavailable.", "browser_not_ready")
        worker = None
        try:
            page = await self._owner.context.new_page()
            worker = BrowserPage()
            worker.context, worker.page = self._owner.context, page
            worker.model_catalog = dict(self._owner.model_catalog)
            worker.model_catalog_observed = self._owner.model_catalog_observed
            worker.catalog_observed_at = self._owner.catalog_observed_at
            worker.is_ready = self._owner.is_ready
            worker.attach_page_listeners()
            return worker
        except Exception:
            await self.close_page(worker)
            raise GatewayError(503, "Browser could not initialize an isolated request page.", "browser_not_ready") from None

    async def acquire(self, scope):
        if scope.admitted:
            raise RuntimeError("Request already owns execution admission")
        continuation = bool(scope.history and scope.history[-1].get("role") == "tool")
        deadline = time.monotonic() + self.timeout
        await self.prune()
        async with self.condition:
            if continuation:
                call_id = scope.history[-1]["tool_call_id"]
                slot = next((s for s in self.slots.values() if s.worker.tool_run.pending and
                             any(c["id"] == call_id for c in s.worker.tool_run.pending["calls"])), None)
                if slot is None or slot.owner != scope.owner or slot.busy or slot.worker.page.is_closed():
                    raise GatewayError(409, "This function round is unavailable, foreign or already in progress.", "tool_continuation_unavailable")
                slot.busy = True
                slot.claim = scope.id
                scope.slot, scope.worker = slot, slot.worker
                scope.original_pending = slot.worker.tool_run.pending
            if not continuation and scope.needs_page and self.quarantined:
                raise GatewayError(503, "A browser page is still being cleaned up.", "browser_cleanup_pending")
            if len(self.queue) >= self.max_queue:
                if scope.slot:
                    scope.slot.busy = False
                    scope.slot = scope.worker = None
                raise GatewayError(429, "Request queue is full.", "request_queue_full")
            self.queue.append(scope)
            try:
                while True:
                    if scope.needs_page and not continuation and self.quarantined:
                        raise GatewayError(503, "A browser page is still being cleaned up.", "browser_cleanup_pending")
                    if self.closing:
                        raise GatewayError(503, "Browser is shutting down.", "browser_not_ready")
                    # Reserve growth headroom for every active task; this is deliberately conservative.
                    waiting = sum(bool(s.tool_capable or s.worker.tool_run.pending) for s in self.slots.values())
                    def eligible(q):
                        memory_ok = (q.original_pending or
                                     self.memory() >= self.reserve + self.tab_bytes*(self.active+1))
                        tool_ok = not q.tool_capable or q.original_pending or waiting+self.reserved_tools < self.max_waiting
                        return memory_ok and tool_ok
                    candidates = sorted(self.queue, key=lambda q: not bool(q.original_pending))
                    first = next((q for q in candidates if eligible(q)), None)
                    if first is scope and self.active < self.max_active:
                        self.active += 1
                        scope.admitted = True
                        if scope.tool_capable and not continuation:
                            self.reserved_tools += 1
                            scope.tool_reserved = True
                        self.queue.remove(scope)
                        self.condition.notify_all()
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise GatewayError(429, "Timed out waiting for browser capacity or available memory.", "request_queue_timeout")
                    with suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(self.condition.wait(), min(.1, remaining))
            except BaseException:
                if scope in self.queue: self.queue.remove(scope)
                if scope.slot:
                    scope.slot.busy = False
                    scope.slot = scope.worker = None
                self.condition.notify_all()
                raise
        if scope.needs_page and not continuation:
            task = asyncio.create_task(self.create_page())
            try:
                scope.worker = await asyncio.shield(task)
                scope.worker.request_id = scope.id
                scope.slot = SimpleNamespace(id=scope.id, owner=scope.owner, worker=scope.worker,
                                             busy=True, tool_capable=scope.tool_capable, claim=scope.id)
                async with self.condition:
                    self.slots[scope.id] = scope.slot
                    if scope.tool_reserved:
                        self.reserved_tools -= 1
                        scope.tool_reserved = False
                    self.condition.notify_all()
            except BaseException:
                with CancelScope(shield=True):
                    with suppress(Exception):
                        if scope.worker is None: scope.worker = await task
                        await self.close_page(scope.worker)
                raise

    async def close_page(self, worker):
        if worker is None: return
        worker.tool_run.clear()
        try:
            if not worker.page.is_closed():
                await asyncio.wait_for(worker.page.close(), 5)
            if not worker.page.is_closed():
                raise RuntimeError("Page remained open after close")
        except Exception:
            self.quarantined[id(worker)] = worker
            logger.warning("Request page cleanup pending; new page admission is suspended.")
        else:
            self.quarantined.pop(id(worker), None)

    async def release(self, scope, delivered=False):
        if scope.released: return
        scope.released = True
        slot = scope.slot
        if slot and slot.claim != scope.id:
            slot = None
            scope.worker = None
        pending = scope.worker.tool_run.pending if scope.worker else None
        # Invalid pre-submit continuations must not destroy the legitimate pending round.
        retain = bool(slot and pending and not scope.worker.page.is_closed() and
                      (pending is scope.original_pending or delivered))
        if scope.worker and not retain:
            await self.close_page(scope.worker)
        async with self.condition:
            if slot:
                if retain:
                    slot.busy = False
                else:
                    self.slots.pop(slot.id, None)
                self._owner.generated_models.update(scope.worker.generated_models)
            if scope.admitted: self.active -= 1
            if scope.tool_reserved: self.reserved_tools -= 1
            if scope.entered: self.incoming -= 1
            self.condition.notify_all()

    async def prune(self):
        expired = list(self.quarantined.values())
        async with self.condition:
            for key, slot in list(self.slots.items()):
                if slot.busy: continue
                slot.worker.tool_run.expire()
                if not slot.worker.tool_run.pending or slot.worker.page.is_closed():
                    expired.append(slot.worker)
                    del self.slots[key]
            self.condition.notify_all()
        await asyncio.gather(*(self.close_page(worker) for worker in expired))

    async def maintenance(self):
        while True:
            await asyncio.sleep(5)
            await self.prune()

    async def start(self):
        self.closing = False
        await self._owner.start()

    async def stop(self):
        async with self.condition:
            self.closing = True
            workers = list({id(w):w for w in [s.worker for s in self.slots.values()]+list(self.quarantined.values())}.values())
            self.slots.clear()
            self.condition.notify_all()
        await asyncio.gather(*(self.close_page(w) for w in workers))
        if hasattr(self._owner, "stop"): await self._owner.stop()

    def diagnostic(self, page_id=None):
        if page_id:
            slot = self.slots.get(page_id)
            if slot is None:
                raise GatewayError(404, "Request page is no longer available.", "page_not_found")
            return slot.worker
        if len(self.slots) > 1:
            raise GatewayError(400, "Multiple request pages are open; specify page_id from health.", "page_id_required")
        return next(iter(self.slots.values())).worker if self.slots else self._owner

    def stats(self):
        return {"max_active": self.max_active, "active": self.active, "queued": len(self.queue),
                "pages": [{"page_id":s.id,"state":"running" if s.busy else "waiting_tools"} for s in self.slots.values()],
                "waiting_tools": sum(not s.busy and bool(s.worker.tool_run.pending) for s in self.slots.values()),
                "cleanup_pending": len(self.quarantined), "max_queue": self.max_queue, "max_waiting_tabs": self.max_waiting,
                "memory_available_mb": self.memory()//MB, "memory_reserve_mb": self.reserve//MB,
                "estimated_new_tab_mb": self.tab_bytes//MB}

class BrowserAdmission:
    def __init__(self, pool): self.pool = pool
    def locked(self): return False  # Capacity waits in the bounded queue rather than fail-fast.
    async def __aenter__(self):
        if self.pool.current is None: raise RuntimeError("Browser admission requires HTTP request ownership")
        await self.pool.acquire(self.pool.current)
    async def __aexit__(self, *exc): pass  # ASGI owns cleanup through the final response body.

class BrowserRequestMiddleware:
    def __init__(self, app, pool): self.app, self.pool = app, pool
    async def __call__(self, scope, receive, send):
        path = scope.get("path")
        if scope["type"] != "http" or scope.get("method") != "POST" or path not in GENERATING | {"/v1/files"}:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        request = self.pool.new_scope(headers.get(b"authorization", b"").decode("latin1"), path in GENERATING)
        started = finished = False
        token = self.pool._scope.set(request)
        async def guarded_receive():
            event = await receive()
            size = len(event.get("body", b""))
            if size and self.pool.memory() < self.pool.reserve + size*2:
                raise GatewayError(503, "Insufficient available memory to receive this request.", "request_memory_exhausted")
            return event
        async def tracked_send(message):
            nonlocal started, finished
            if message["type"] == "http.response.start":
                started = True
                request.status = message["status"]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                finished = True
        try:
            await self.pool.enter(request)
            await self.app(scope, guarded_receive, tracked_send)
        except GatewayError as error:
            if started: raise
            response = JSONResponse({"error":provider_error(error)}, status_code=error.status_code)
            await response(scope, receive, tracked_send)
        finally:
            with CancelScope(shield=True):
                await self.pool.release(request, delivered=finished and request.status < 400)
            self.pool._scope.reset(token)
