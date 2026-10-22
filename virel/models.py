"""Observed AI Studio model cards; no inferred provider model registry."""
import re

IMAGE_MODEL_ICONS = {'gempix', 'image_edit_auto'}

MODEL_SELECTOR = 'button.model-selector-card,button.model-selector-trigger[aria-label="Select primary model"]'
MODEL_ROWS = 'ms-model-carousel-row button.content-button[id^="model-carousel-row-models/"]'
READ_MODEL_ROWS = r'''async () => {
    const dialogContainer = document.querySelector('mat-dialog-content, .cdk-virtual-scroll-viewport, [role="dialog"], ms-model-picker');
    const collected = new Map();
    function scrape() {
        const buttons = Array.from(document.querySelectorAll('button.content-button, ms-model-carousel-row button, ms-model-card button, .model-card button'));
        for (const button of buttons) {
            const row = button.closest('ms-model-carousel-row') || button.parentElement;
            let id = (button.querySelector('.model-subtitle')?.textContent || '').trim();
            if (!id && button.id && button.id.includes('model-carousel-row-models/')) {
                id = button.id.replace('model-carousel-row-models/', '');
            }
            if (!id && button.id && /gemini-[a-z0-9._-]+/i.test(button.id)) {
                id = button.id.match(/gemini-[a-z0-9._-]+/i)[0];
            }
            if (!id) {
                const text = button.innerText || '';
                const m = text.match(/\b(gemini-[a-z0-9._-]+)\b/i);
                if (m) id = m[1].toLowerCase();
            }
            if (!id && button.id) {
                id = button.id.replace('model-carousel-row-models/', '');
            }
            if (!id || collected.has(id)) continue;
            const text = button.innerText || '';
            const icon = button.querySelector('[data-test-model-icon]');
            const paid = Array.from((row || button).querySelectorAll('ms-badge')).some(el => (el.textContent || '').trim().toLowerCase() === 'paid');
            const disabled = button.disabled || button.getAttribute('aria-disabled') === 'true' || (row && row.getAttribute('aria-disabled') === 'true');
            const resolved = text.match(/Points to\s+([a-z0-9][a-z0-9._-]+)/i)?.[1] || null;
            collected.set(id, {
                id,
                label: (button.querySelector('.model-title-text')?.textContent || '').trim() || id,
                icon: (icon?.textContent || '').trim() || icon?.getAttribute('data-test-model-icon') || '',
                paid,
                disabled,
                resolved_id: resolved
            });
        }
    }
    scrape();
    if (dialogContainer && dialogContainer.scrollHeight > dialogContainer.clientHeight) {
        let lastTop = -1;
        while (dialogContainer.scrollTop !== lastTop && dialogContainer.scrollTop + dialogContainer.clientHeight < dialogContainer.scrollHeight + 20) {
            lastTop = dialogContainer.scrollTop;
            dialogContainer.scrollTop += 350;
            await new Promise(r => setTimeout(r, 60));
            scrape();
        }
        dialogContainer.scrollTop = 0;
    }
    return Array.from(collected.values());
}'''


def catalog_from_rows(rows):
    result = {}
    for row in rows:
        identifier = row.get('id', '')
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-z0-9][a-z0-9._-]*', identifier):
            continue
        is_image = row.get('icon') in IMAGE_MODEL_ICONS or 'image' in identifier
        is_speech = identifier.endswith('-tts') or '-tts-' in identifier or (row.get('icon') == 'audio_magic_eraser' and identifier.endswith('-tts'))
        if row.get('paid') or row.get('disabled'):
            status = 'unavailable'
        elif row.get('icon') == 'audio_magic_eraser' and not identifier.endswith('-tts'):
            status = 'unsupported'
        else:
            status = 'selectable'
        output_mods = ['image'] if is_image else (['audio'] if is_speech else ['text'])
        item = {'id': identifier, 'display_name': row.get('label') or identifier, 'status': status,
            'capabilities': {'input_modalities': None, 'output_modalities': output_mods, 'ui_category_icon': row.get('icon') or ('spark' if not is_image and not is_speech else ('gempix' if is_image else 'audio_magic_eraser')), 'source': 'ai_studio_ui'}}
        resolved = row.get('resolved_id')
        if isinstance(resolved, str) and re.fullmatch(r'[a-z0-9][a-z0-9._-]*', resolved):
            item['resolved_id'] = resolved
        result[identifier] = item
    for item in result.values():
        if 'resolved_id' not in item:
            continue
        seen, current = {item['id']}, item
        while 'resolved_id' in current:
            target = result.get(current['resolved_id'])
            if target is None or target['id'] in seen:
                item['status'] = 'unavailable'
                break
            if target['status'] != 'selectable':
                item['status'] = target['status']
                break
            seen.add(target['id'])
            current = target
        else:
            item['resolved_id'] = current['id']
    return result


def selected_card_id(label, catalog):
    identifiers = [line.strip() for line in label.splitlines() if line.strip() in catalog]
    if len(identifiers) != 1:
        return None
    return identifiers[0]


def selected_id(label, catalog):
    identifier = selected_card_id(label, catalog)
    if identifier is None:
        return None
    item = catalog[identifier]
    return item.get('resolved_id', item['id'])


def desktop_aliases(catalog):
    """User-authorized Desktop routing names; native UI IDs stay authoritative."""
    from .errors import GatewayError
    aliases = {}
    for identifier, item in catalog.items():
        if item["status"] != "selectable":
            continue
        alias = identifier.replace("gemini", "claude") if "gemini" in identifier else (
            identifier if identifier.startswith("claude-") else "claude-" + identifier)
        if alias in aliases:
            raise GatewayError(503, "Observed models have conflicting Desktop aliases.", "model_alias_conflict")
        aliases[alias] = identifier
    return aliases
