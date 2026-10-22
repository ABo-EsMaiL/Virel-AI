"""One ephemeral native function round; no stored conversation or tool execution."""
import hashlib
import json
import time
from .errors import GatewayError


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def canonical_arguments(name, value, routing_tools):
    args = json.loads(value)
    # n8n toolkit histories add their own tool name as routing metadata.
    if name in routing_tools and args.get("tool") == name:
        args.pop("tool")
    return args


def canonical(history, routing_tools=()):
    result = []
    for turn in history:
        if turn.get("tool_calls"):
            calls = [{"id": c["id"], "name": c["name"], "arguments": canonical_arguments(c["name"], c["arguments"], routing_tools)} for c in turn["tool_calls"]]
            if result and result[-1].get("tool_calls"):
                result[-1]["tool_calls"].extend(calls)
            else: result.append({"role": "assistant", "tool_calls": calls})
        else: result.append(turn)
    return result


def conversation(history):
    """Keep instruction roles/positions bound while allowing their content to refresh."""
    return [{"role": turn["role"]} if turn.get("role") in ("system", "developer") else turn for turn in history]


def instructions(history):
    return [turn for turn in history if turn.get("role") in ("system", "developer")]

def result_context(history):
    """Separate authenticated caller context appended after a client's tool results."""
    end = len(history or [])
    while end and history[end-1].get("role") in ("user", "system", "developer") and not history[end-1].get("tool_calls"):
        end -= 1
    if end and history[end-1].get("role") == "tool":
        return history[:end], history[end:]
    return history or [], []


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

    def remember(self, history, calls, config, anchor="", response_text="", text="", owner="", tool_schemas=None, visibility=None, internal_generated=False):
        # Typed dictionary keys are caller data, including a key named tool.
        routing_tools = tuple(name for name, schema in (tool_schemas or {}).items()
                              if "tool" not in schema.get("properties", {}) and
                              not (isinstance(schema.get("additionalProperties"),dict) and schema["additionalProperties"]))
        normalized = canonical(history, routing_tools)
        self.pending = {"prefix": digest(conversation(normalized)), "config": config, "visibility": visibility,
                        "owner": owner, "routing_tools": routing_tools, "instructions": digest(instructions(normalized)),
                        "text": digest(text), "anchor": anchor, "response_hash": digest(response_text),
                        "deadline": time.monotonic() + self.ttl, "internal_generated": internal_generated,
                        "calls": [{"id": call["id"], "name": call["function"]["name"],
                                   "arguments_hash": digest(canonical_arguments(call["function"]["name"], call["function"]["arguments"], routing_tools))} for call in calls]}

    def resolve(self, history, config, owner=""):
        self.expire()
        history, context = result_context(history)
        if not history or history[-1].get("role") != "tool":
            if self.pending and owner == self.pending["owner"]:
                self.clear()
            self.require_idle()
            return None
        if not self.pending:
            raise GatewayError(409, "This function round is no longer available. Start a new agent execution; results were not replayed.", "tool_continuation_unavailable")
        normalized = canonical(history, self.pending.get("routing_tools", ()))
        results, supplied = {}, {}
        expected = {c["id"]: {k: c[k] for k in ("id", "name", "arguments_hash")} for c in self.pending["calls"]}
        # Clients may interleave each call/result pair rather than replay one assistant batch.
        while normalized and (len(results) < len(expected) or len(supplied) < len(expected)):
            turn = normalized[-1]
            if turn.get("role") == "tool":
                call_id = turn["tool_call_id"]
                if call_id not in expected or call_id in results:
                    break
                results[call_id] = turn["content"]
            elif turn.get("tool_calls"):
                calls = turn["tool_calls"]
                batch = {c["id"]: {"id": c["id"], "name": c["name"], "arguments_hash": digest(c["arguments"])} for c in calls}
                if len(batch) != len(calls) or any(call_id not in expected or call_id in supplied for call_id in batch):
                    break
                supplied.update(batch)
            else:
                break
            normalized.pop()
        prefix = digest(conversation(normalized))
        # Native clients can omit text accompanying a function request.
        if prefix != self.pending["prefix"] and normalized and normalized[-1].get("role") == "assistant" and digest(normalized[-1].get("content", "")) == self.pending["text"]:
            prefix = digest(conversation(normalized[:-1]))
        if owner != self.pending["owner"] or config != self.pending["config"] or prefix != self.pending["prefix"] or supplied != expected or set(results) != set(expected):
            raise GatewayError(409, "Function IDs, previous history, caller or settings do not match the pending round.", "tool_continuation_conflict")
        reply = {"results": [{"call_id": c["id"], "name": c["name"], "output": results[c["id"]]} for c in self.pending["calls"]],
                 "anchor": self.pending["anchor"], "response_hash": self.pending["response_hash"], "internal_generated": self.pending.get("internal_generated", False)}
        if context:
            reply["caller_messages"] = context
        current_instructions = instructions(normalized)
        if digest(current_instructions) != self.pending["instructions"]:
            reply["caller_instructions"] = current_instructions
        self.clear()
        return reply
