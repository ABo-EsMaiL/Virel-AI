"""Actual AI Studio function controls; no tool execution or prose inference."""
import json
from .errors import GatewayError


async def disable_functions(page):
    switch = page.locator('button[role="switch"][aria-label="Function calling"]').first
    if await switch.count() and await switch.get_attribute('aria-checked') == 'true':
        await switch.click(timeout=5000)
        if await switch.get_attribute('aria-checked') != 'false':
            raise GatewayError(503, "AI Studio function mode could not be disabled.", "settings_unavailable")


def _canonical(value):
    if isinstance(value, list): return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()
                if not (k == "propertyOrdering" and value.get("type") == "object")}
    return value


async def ensure_functions(page, declarations):
    try:
        await disable_functions(page)
        if not declarations: return
        for label in ('Grounding with Google Search', 'Browse the url context'):
            control = page.locator(f'button[role="switch"][aria-label="{label}"]').first
            if await control.count() and await control.get_attribute('aria-checked') == 'true':
                await control.click(timeout=5000)
            if await control.count() and await control.get_attribute('aria-checked') != 'false':
                raise GatewayError(503, "Incompatible AI Studio tools could not be disabled.", "settings_unavailable")
        switch = page.locator('button[role="switch"][aria-label="Function calling"]').first
        if not await switch.count() or not await switch.is_enabled():
            raise GatewayError(400, "This AI Studio model does not expose function calling.", "unsupported_capability")
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
        if _canonical(observed) != declarations:
            raise GatewayError(503, "AI Studio function declarations did not match the request.", "settings_unavailable")
        await dialog.locator('button[aria-label="close"]').click(timeout=5000)
        await dialog.wait_for(state='hidden', timeout=5000)
    except GatewayError:
        raise
    except Exception:
        raise GatewayError(503, "AI Studio function declarations could not be configured and verified.", "settings_unavailable") from None
