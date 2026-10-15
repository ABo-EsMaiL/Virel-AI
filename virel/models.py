"""Observed AI Studio model cards; no inferred provider model registry."""
import re

MODEL_SELECTOR = 'button.model-selector-card'
MODEL_ROWS = 'ms-model-carousel-row button.content-button[id^="model-carousel-row-models/"]'
READ_MODEL_ROWS = r'''() => Array.from(document.querySelectorAll('ms-model-carousel-row')).map(row => {
    const button = row.querySelector('button.content-button[id^="model-carousel-row-models/"]');
    if (!button) return null;
    const id = button.id.replace('model-carousel-row-models/', '');
    const text = button.innerText || '';
    return {id, label:(button.querySelector('.model-title-text')?.textContent || '').trim(),
        icon:(button.querySelector('[data-test-model-icon]')?.textContent || '').trim(),
        paid:Array.from(button.querySelectorAll('ms-badge')).some(el => (el.textContent || '').trim().toLowerCase() === 'paid'),
        disabled:button.disabled || button.getAttribute('aria-disabled') === 'true' || row.getAttribute('aria-disabled') === 'true',
        resolved_id:text.match(/Points to\s+([a-z0-9][a-z0-9._-]+)/i)?.[1] || null};
}).filter(Boolean)'''


def catalog_from_rows(rows):
    result = {}
    for row in rows:
        identifier = row.get('id', '')
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-z0-9][a-z0-9._-]*', identifier):
            continue
        status = 'unavailable' if row.get('paid') or row.get('disabled') else ('selectable' if row.get('icon') == 'spark' else 'unsupported')
        item = {'id': identifier, 'display_name': row.get('label') or identifier, 'status': status,
            'capabilities': {'input_modalities': None, 'output_modalities': None, 'ui_category_icon': row.get('icon'), 'source': 'ai_studio_ui'}}
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


def selected_id(label, catalog):
    identifiers = [line.strip() for line in label.splitlines() if line.strip() in catalog]
    if len(identifiers) != 1:
        return None
    item = catalog[identifiers[0]]
    return item.get('resolved_id', item['id'])
