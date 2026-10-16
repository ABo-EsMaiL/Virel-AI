"""Native function batch transport; the external client executes every tool."""
import asyncio
import json
from .errors import GatewayError
from .tool_runs import digest

BATCH_NAME = "virel_client_tools"


def batch_declaration(declarations):
    if not declarations:
        return []
    items = {"type": "object", "properties": {
        fn["name"]: fn["parameters"] for fn in declarations}}
    return [{"name": BATCH_NAME,
             "description": "Request external tools in calls order. Each array entry has exactly one property: the tool name with its arguments object. Use separate entries for multiple calls, including repeated tools. The external client executes them; never execute tools yourself.",
             "parameters": {"type": "object", "properties": {
                 "calls": {"type": "array", "items": items}}, "required": ["calls"]}}]


def unpack_calls(calls):
    if not isinstance(calls, list):
        raise GatewayError(502, "The native client calls must be an array.", "invalid_upstream_tool_call")
    result = []
    for entry in calls:
        if not isinstance(entry, dict) or len(entry) != 1:
            raise GatewayError(502, "Each native client call must contain exactly one tool name.", "invalid_upstream_tool_call")
        name, value = next(iter(entry.items()))
        if not isinstance(value, dict):
            raise GatewayError(502, "Native client tool arguments must be a JSON object.", "invalid_upstream_tool_call")
        result.append({"name": name, "arguments": value})
    return result


async def disable_structured(page):
    toggle = page.locator('button[role="switch"][aria-label="Structured outputs"]').first
    if await toggle.count() and await toggle.get_attribute('aria-checked') == 'true':
        await toggle.click(timeout=5000)
        if await toggle.get_attribute('aria-checked') != 'false':
            raise GatewayError(503, "AI Studio structured mode could not be disabled.", "settings_unavailable")


def current_turn(page, anchor):
    return page.locator('ms-chat-turn[id=' + json.dumps(anchor) + ']')


async def verify_continuation(page, continuation, state):
    toggle = page.locator('button[role="switch"][aria-label="Function calling"]').first
    try:
        calls = [{"name": c["name"], "arguments": json.loads(c["arguments"])} for c in state.get("function_calls", [])]
    except (KeyError, ValueError, TypeError):
        calls = None
    if (not continuation["anchor"] or state.get("model_turn_id") != continuation["anchor"] or
            digest(calls) != continuation["response_hash"] or state.get("is_running") or
            not await toggle.count() or await toggle.get_attribute('aria-checked') != 'true'):
        raise GatewayError(409, "The pending native function call no longer matches the browser page.", "tool_continuation_conflict")


async def prepare_result(page, prompt, continuation):
    """Fill one native response with the whole opaque result batch; caller clicks once."""
    try:
        turn = current_turn(page, continuation["anchor"])
        chunk = turn.locator('ms-function-call-chunk')
        field = chunk.locator('input[aria-label="Enter a function response"]')
        button = chunk.locator('button[type="submit"]')
        if await chunk.count() != 1 or await field.count() != 1 or await button.count() != 1:
            raise GatewayError(409, "The native function response control changed.", "tool_continuation_conflict")
        value = json.dumps({"output": prompt}, ensure_ascii=False)
        await field.fill(value, timeout=5000)
        await field.press('Space')
        await field.press('Backspace')
        await field.press('Tab')
        deadline = asyncio.get_running_loop().time() + 5
        while asyncio.get_running_loop().time() < deadline:
            if await button.is_enabled() and await button.get_attribute('aria-disabled') != 'true':
                if await field.input_value() != value:
                    break
                return button
            await asyncio.sleep(.1)
        raise GatewayError(503, "The native function response was not ready; nothing was sent.", "browser_not_ready")
    except GatewayError:
        raise
    except Exception:
        raise GatewayError(503, "The native function response could not be prepared; nothing was sent.", "browser_not_ready") from None
