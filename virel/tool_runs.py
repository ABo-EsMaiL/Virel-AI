"""One ephemeral native function round; no stored conversation or tool execution."""
import hashlib
import json
import time
from .errors import GatewayError


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def canonical(history):
    result = []
    for turn in history:
        if turn.get("tool_calls"):
            calls = [{"id": c["id"], "name": c["name"], "arguments": json.loads(c["arguments"])} for c in turn["tool_calls"]]
            if result and result[-1].get("tool_calls"):
                result[-1]["tool_calls"].extend(calls)
            else: result.append({"role": "assistant", "tool_calls": calls})
        else: result.append(turn)
    return result


class ToolRun:
    def __init__(self, ttl):
        self.ttl = ttl
        self.pending = None

    def clear(self):
        self.pending = None

    def expire(self):
        if self.pending and time.monotonic() >= self.pending["deadline"]: self.clear()

    def require_idle(self):
        self.expire()
        if self.pending:
            raise GatewayError(429, "The browser is waiting for this agent's function result. Finish that loop or wait for its idle timeout.", "tool_run_busy")

    def remember(self, history, calls, config, anchor="", response_text="", text=""):
        self.pending = {"prefix": digest(canonical(history)), "config": config,
                        "text": digest(text), "anchor": anchor, "response_hash": digest(response_text),
                        "deadline": time.monotonic() + self.ttl,
                        "calls": [{"id": call["id"], "name": call["function"]["name"],
                                   "arguments_hash": digest(json.loads(call["function"]["arguments"]))} for call in calls]}

    def resolve(self, history, config):
        self.expire()
        if not history or history[-1].get("role") != "tool":
            self.require_idle()
            return None
        if not self.pending:
            raise GatewayError(409, "This function round is no longer available. Start a new agent execution; results were not replayed.", "tool_continuation_unavailable")
        normalized = canonical(history)
        results = {}
        while normalized and normalized[-1].get("role") == "tool":
            turn = normalized.pop()
            results[turn["tool_call_id"]] = turn["content"]
        calls = normalized.pop().get("tool_calls", []) if normalized else []
        supplied = [{"id": c["id"], "name": c["name"], "arguments_hash": digest(c["arguments"])} for c in calls]
        expected = [{k: c[k] for k in ("id", "name", "arguments_hash")} for c in self.pending["calls"]]
        prefix = digest(normalized)
        # Native clients can omit text accompanying a function request.
        if prefix != self.pending["prefix"] and normalized and normalized[-1].get("role") == "assistant" and digest(normalized[-1].get("content", "")) == self.pending["text"]:
            prefix = digest(normalized[:-1])
        if config != self.pending["config"] or prefix != self.pending["prefix"] or supplied != expected or set(results) != {c["id"] for c in expected}:
            raise GatewayError(409, "Function IDs, previous history, caller or settings do not match the pending round.", "tool_continuation_conflict")
        reply = {"results": [{"call_id": c["id"], "name": c["name"], "output": results[c["id"]]} for c in self.pending["calls"]],
                 "anchor": self.pending["anchor"], "response_hash": self.pending["response_hash"]}
        self.clear()
        return reply
