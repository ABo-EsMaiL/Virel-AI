"""Observe the browser's own generation response; never call Google APIs."""
import asyncio
from dataclasses import dataclass
import json
from urllib.parse import unquote, urlsplit


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None

    def chat(self):
        result = {"prompt_tokens": self.input_tokens, "completion_tokens": self.output_tokens, "total_tokens": self.total_tokens}
        if self.reasoning_tokens is not None:
            result["completion_tokens_details"] = {"reasoning_tokens": self.reasoning_tokens}
        if self.cached_tokens is not None:
            result["prompt_tokens_details"] = {"cached_tokens": self.cached_tokens}
        return result

    def responses(self):
        result = {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens, "total_tokens": self.total_tokens}
        if self.reasoning_tokens is not None:
            result["output_tokens_details"] = {"reasoning_tokens": self.reasoning_tokens}
        if self.cached_tokens is not None:
            result["input_tokens_details"] = {"cached_tokens": self.cached_tokens}
        return result


def _integer(value):
    return type(value) is int and value >= 0


def parse_usage(text):
    """Decode observed array-wire field numbers, validated by Google's proto.

    googleapis/googleapis: generativelanguage/v1beta/generative_service.proto.
    Unknown framing/fields remain unavailable rather than guessing positions.
    """
    if len(text) > 2 * 1024 * 1024:
        return None
    try:
        packet = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(packet, list) or len(packet) != 1 or not isinstance(packet[0], list):
        return None
    latest = None
    for frame in packet[0]:
        if not isinstance(frame, list) or len(frame) < 3 or not isinstance(frame[0], list):
            continue
        completed = any(
            isinstance(candidate, list) and len(candidate) > 1
            and isinstance(candidate[0], list) and len(candidate[0]) > 1
            and candidate[0][1] == "model" and _integer(candidate[1]) and candidate[1] > 0
            for candidate in frame[0]
        )
        fields = frame[2]
        if not completed or not isinstance(fields, list) or len(fields) < 3:
            continue
        prompt, visible, total = fields[:3]
        cached = fields[3] if len(fields) > 3 else None
        tool_input = fields[7] if len(fields) > 7 else None
        thinking = fields[9] if len(fields) > 9 else None
        if not all(_integer(value) for value in (prompt, visible, total)):
            continue
        if any(value is not None and not _integer(value) for value in (cached, tool_input, thinking)):
            continue
        input_tokens = prompt + (tool_input or 0)
        output_tokens = visible + (thinking or 0)
        if total != input_tokens + output_tokens or (cached is not None and cached > prompt):
            continue
        latest = TokenUsage(input_tokens, output_tokens, total, thinking, cached)
    return latest


def parse_finish_reason(text):
    """Read only an observed MAX_TOKENS candidate (proto field2, enum2)."""
    if not isinstance(text, str) or len(text) > 2 * 1024 * 1024:
        return None
    try:
        packet = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(packet, list) or len(packet) != 1 or not isinstance(packet[0], list):
        return None
    latest = None
    for frame in packet[0]:
        if not isinstance(frame, list) or len(frame) < 3 or not isinstance(frame[0], list) or not frame[0]:
            continue
        candidates = frame[0]
        if any(not isinstance(c, list) or len(c) < 2 or
               not (c[0] in (None, []) or isinstance(c[0], list) and len(c[0]) > 1 and c[0][1] == "model")
               for c in candidates):
            return None
        reasons = [c[1] for c in candidates]
        if any(type(reason) is not int for reason in reasons):
            return None
        if any(reason <= 0 for reason in reasons):
            latest = None
            continue
        latest = "max_tokens" if all(reason == 2 for reason in reasons) else None
    return latest


class BrowserUsageObserver:
    def __init__(self):
        self.active_id = None
        self.prompt = ""
        self.last_usage = None
        self.last_finish_reason = None
        self.requests = {}
        self.pending = {}

    def begin(self, attempt_id, prompt):
        self.active_id = attempt_id
        self.prompt = prompt
        self.last_usage = None
        self.last_finish_reason = None
        self.requests.clear()

    def on_request(self, request):
        url = urlsplit(request.url)
        if (not self.active_id or not self.prompt or request.method != "POST"
                or url.scheme != "https" or url.hostname not in {"aistudio.google.com", "alkali-pa.clients6.google.com", "alkalimakersuite-pa.clients6.google.com"}
                or not url.path.endswith(".MakerSuiteService/GenerateContent")):
            return
        body = unquote(request.post_data or "")
        needles = (self.prompt, json.dumps(self.prompt, ensure_ascii=False)[1:-1], json.dumps(self.prompt, ensure_ascii=True)[1:-1])
        if any(needle in body for needle in needles):
            self.requests[request] = self.active_id

    def on_response(self, response):
        attempt_id = self.requests.pop(response.request, None)
        if attempt_id is None or response.status != 200:
            return
        task = asyncio.create_task(self._read(response, attempt_id))
        self.pending[task] = attempt_id
        task.add_done_callback(lambda done: self.pending.pop(done, None))

    async def _read(self, response, attempt_id):
        try:
            text = await response.text()
            usage = parse_usage(text)
            if attempt_id == self.active_id:
                self.last_finish_reason = parse_finish_reason(text)
                if usage is not None:
                    self.last_usage = usage
        except Exception:
            # Metadata is optional; failures must not reuse previous request counts.
            pass

    async def finish(self, attempt_id):
        owned = [task for task, owner in self.pending.items() if owner == attempt_id]
        usage = None
        try:
            if owned:
                await asyncio.wait(owned, timeout=2)
        finally:
            for task in owned:
                if not task.done():
                    task.cancel()
                self.pending.pop(task, None)
            if self.active_id == attempt_id:
                usage = self.last_usage
                self.active_id = None
                self.prompt = ""
                self.requests.clear()
        return usage
