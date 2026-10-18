"""Actual AI Studio function controls; no tool execution or prose inference."""
import json
import logging
from .errors import GatewayError

logger = logging.getLogger("virel.webhook")


async def disable_functions(page):
    switch = page.locator('button[role="switch"][aria-label="Function calling"]').first
    if await switch.count() and await switch.get_attribute('aria-checked') == 'true':
        await switch.click(timeout=5000)
        if await switch.get_attribute('aria-checked') != 'false':
            raise GatewayError(503, "AI Studio function mode could not be disabled.", "settings_unavailable")


def _canonical(value):
    if isinstance(value, list): return [_canonical(item) for item in value]
    if isinstance(value, dict):
        # AI Studio omits the empty properties map on zero-argument objects.
        result = {k: _canonical(v) for k, v in value.items()
                  if not (value.get("type") == "object" and
                          (k == "propertyOrdering" or (k == "properties" and v == {})))}
        # Save reorders required field names; membership, not position, defines the schema.
        required = result.get("required")
        if value.get("type") == "object" and isinstance(required, list) and all(isinstance(k, str) for k in required):
            result["required"] = sorted(required)
        return result
    return value



def _difference(expected, observed, path="declarations"):
    """Return a bounded structural location, never schema values or client property names."""
    if type(expected) is not type(observed):
        return path[:512] + ": type changed"
    if isinstance(expected, dict):
        keywords = {"type", "properties", "items", "required", "enum", "description",
                    "parameters", "name", "propertyOrdering", "nullable", "format", "default"}
        if expected.keys() != observed.keys():
            missing = sorted((expected.keys() - observed.keys()) & keywords)
            added = sorted((observed.keys() - expected.keys()) & keywords)
            detail = " missing=" + ",".join(missing) + " added=" + ",".join(added) if missing or added else ""
            return path[:512] + ": keys changed" + detail
        for index, (key, value) in enumerate(expected.items()):
            label = key if key in keywords else "[" + str(index) + "]"
            difference = _difference(value, observed[key], path + "/" + label)
            if difference:
                return difference
    elif isinstance(expected, list):
        if len(expected) != len(observed):
            return path[:512] + ": length changed"
        for index, (value, other) in enumerate(zip(expected, observed)):
            difference = _difference(value, other, path + "/" + str(index))
            if difference:
                return difference
    elif expected != observed:
        return path[:512] + ": value changed"
    return None

async def ensure_functions(page, declarations, *, preserve_pending=False):
    try:
        if not preserve_pending:
            await disable_functions(page)
        if not declarations: return
        for label in ('Grounding with Google Search', 'Browse the url context'):
            control = page.locator(f'button[role="switch"][aria-label="{label}"]').first
            if await control.count() and await control.get_attribute('aria-checked') == 'true':
                await control.click(timeout=5000)
            if await control.count() and await control.get_attribute('aria-checked') != 'false':
                raise GatewayError(503, "Incompatible AI Studio tools could not be disabled.", "settings_unavailable")
        switch = page.locator('button[role="switch"][aria-label="Function calling"]').first
        if not await switch.count() or (not preserve_pending and not await switch.is_enabled()):
            raise GatewayError(400, "This AI Studio model does not expose function calling.", "unsupported_capability")
        if not preserve_pending:
            await switch.click(timeout=5000)
        if await switch.get_attribute('aria-checked') != 'true':
            raise GatewayError(503, "AI Studio function mode could not be verified.", "settings_unavailable")
        edit = page.get_by_role('button', name='Edit function declarations', exact=True)
        await edit.click(timeout=5000)
        dialog = page.locator('ms-edit-function-declarations-dialog')
        await dialog.get_by_text('Code Editor', exact=True).click(timeout=5000)
        editor = dialog.locator('textarea')
        await editor.click(timeout=5000)
        await editor.fill(json.dumps(declarations), timeout=5000)
        await editor.press('Tab')
        await dialog.get_by_role('button', name='Save the current function declarations', exact=True).click(timeout=5000)
        await dialog.wait_for(state='hidden', timeout=5000)
        await edit.click(timeout=5000)
        await dialog.get_by_text('Code Editor', exact=True).click(timeout=5000)
        observed = json.loads(await editor.input_value())
        await dialog.locator('button[aria-label="close"]').click(timeout=5000)
        await dialog.wait_for(state='hidden', timeout=5000)
        if _canonical(observed) != _canonical(declarations):
            difference = _difference(_canonical(declarations), _canonical(observed))
            logger.warning("AI Studio declaration readback mismatch: %s", difference)
            raise GatewayError(503, "AI Studio function declarations did not match the request.",
                               "settings_unavailable", param=difference)
    except GatewayError:
        raise
    except Exception:
        raise GatewayError(503, "AI Studio function declarations could not be configured and verified.", "settings_unavailable") from None
