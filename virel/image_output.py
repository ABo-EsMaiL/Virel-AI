"""Native image options and bounded current-response image extraction."""
import base64
import binascii
import re
from .config import DEFAULT_IMAGE_MODEL, MAX_GENERATED_IMAGE_BYTES
from .errors import GatewayError
from .images import validate_image_bytes


def image_options(body):
    if not isinstance(body, dict):
        raise GatewayError(400, 'Expected image options object.', 'invalid_request')
    if set(body) - {'model', 'prompt', 'n', 'size', 'quality', 'response_format', 'output_format'}:
        raise GatewayError(400, 'Unsupported image parameter.', 'unsupported_parameter')
    requested = body.get('model', DEFAULT_IMAGE_MODEL)
    if not isinstance(requested, str) or not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,127}', requested):
        raise GatewayError(400, 'Use a valid observed image model ID.', 'invalid_request')
    prompt = body.get('prompt')
    if not isinstance(prompt, str) or not prompt.strip():
        raise GatewayError(400, 'A nonempty image prompt is required.', 'empty_prompt')
    if type(body.get('n', 1)) not in (int, str) or str(body.get('n', 1)) != '1':
        raise GatewayError(400, 'Only one output image is supported.', 'unsupported_parameter')
    if body.get('response_format', 'b64_json') != 'b64_json' or body.get('quality', 'auto') != 'auto' or body.get('output_format', 'png') != 'png':
        raise GatewayError(400, 'Use base64 output, auto quality and original PNG format.', 'unsupported_parameter')
    size = body.get('size', 'auto')
    if size not in ('auto', '1024x1024'):
        raise GatewayError(400, 'Supported image sizes are auto and 1024x1024.', 'unsupported_parameter')
    actual = DEFAULT_IMAGE_MODEL if requested == 'gpt-image-1' else requested
    return requested, actual, prompt, size


async def ensure_image_settings(page, size):
    mode = page.locator('button[role="radio"]').filter(has_text=re.compile(r'Images only')).first
    await mode.wait_for(state='visible', timeout=6000)
    if await mode.get_attribute('aria-checked') != 'true':
        await mode.click()
    if await mode.get_attribute('aria-checked') != 'true':
        raise GatewayError(503, 'AI Studio image output mode could not be verified.', 'settings_unavailable')
    for label, target in [('Aspect ratio', '1:1' if size == '1024x1024' else 'Auto'), ('Resolution', '1K')]:
        control = page.locator('mat-select[aria-label="'+label+'"]').first
        await control.wait_for(state='visible', timeout=6000)
        value = control.locator('.mat-mdc-select-min-line').first
        if not await value.count():
            value = control
        if (await value.inner_text()).strip() != target:
            await control.click()
            options = page.locator('mat-option:visible')
            for option in await options.all():
                if (await option.inner_text()).strip() == target:
                    await option.click()
                    await options.first.wait_for(state='hidden', timeout=2000)
                    break
            else:
                await page.keyboard.press('Escape')
                raise GatewayError(400, 'Requested image setting is unavailable for this model.', 'unsupported_parameter')
        if (await value.inner_text()).strip() != target:
            raise GatewayError(503, 'AI Studio image setting could not be verified.', 'settings_unavailable')


READ_IMAGE_OUTPUT = r"""async ({initial, includeData, maxBytes}) => {
    const turns = Array.from(document.querySelectorAll('ms-chat-turn'));
    const user = t => Boolean(t.querySelector('.user-prompt-container')) || t.getAttribute('data-turn-role') === 'user';
    const model = t => !user(t) && (Boolean(t.querySelector('.model-prompt-container')) || t.getAttribute('data-turn-role') === 'model');
    const models = turns.filter(model);
    const lastUser = turns.findLastIndex(user);
    const current = new Set(models.slice(initial).filter(t => turns.indexOf(t) > lastUser));
    if (Array.from(current).some(t => /\bImage recitation block\b/i.test(t.innerText || ''))) return {error:'image_recitation_block'};
    const images = Array.from(current).flatMap(t => Array.from(t.querySelectorAll('ms-image-chunk .image-container img')))
        .filter(e => !e.closest('ms-thought-chunk,.thought-activity-host,ms-grounding-chip,ms-citation-chunk') && e.getClientRects().length);
    const ready = images.length > 0 && images.every(e => e.complete && e.naturalWidth > 0 && e.naturalHeight > 0);
    const result = {count:images.length, ready, broken:images.some(e=>e.complete && (e.currentSrc || e.getAttribute('src')) && !e.naturalWidth),
        identity:images.map(e=>`${(e.currentSrc||e.src).length}:${e.naturalWidth}x${e.naturalHeight}:${e.complete}`).join('|')};
    if (!includeData) return result;
    if (images.length !== 1 || !ready) return {error:'missing_image'};
    const src = images[0].currentSrc || images[0].src;
    const maxEncoded = 4 * Math.ceil(maxBytes/3) + 100;
    if (/^data:image\/(png|jpeg|webp);base64,/.test(src)) {
        return src.length <= maxEncoded ? {...result, data:src} : {error:'image_too_large'};
    }
    if (location.origin !== 'https://aistudio.google.com' || !src.startsWith('blob:'+location.origin+'/')) return {error:'unsupported_asset'};
    const abort = new AbortController(), timer = setTimeout(()=>abort.abort(),15000);
    try {
        const response = await fetch(src,{signal:abort.signal});
        if (!response.ok || Number(response.headers.get('content-length')) > maxBytes || !response.body) return {error:'invalid_asset'};
        const reader = response.body.getReader(), chunks=[]; let total=0;
        while (true) {
            const {value,done}=await reader.read(); if(done) break;
            total+=value.byteLength;
            if(total>maxBytes) {await reader.cancel();return {error:'image_too_large'};}
            chunks.push(value);
        }
        const blob = new Blob(chunks,{type:response.headers.get('content-type')||'image/png'});
        const data = await new Promise((resolve,reject)=>{const file=new FileReader();file.onload=()=>resolve(file.result);file.onerror=reject;file.readAsDataURL(blob);});
        return data.length <= maxEncoded ? {...result,data} : {error:'image_too_large'};
    } catch {return {error:'invalid_asset'};} finally {clearTimeout(timer);}
}"""


async def read_image_output(page, initial, include_data=False):
    result = await page.evaluate(READ_IMAGE_OUTPUT, {'initial': initial, 'includeData': include_data, 'maxBytes': MAX_GENERATED_IMAGE_BYTES})
    if result.get('error') == 'image_recitation_block':
        raise GatewayError(502, 'AI Studio blocked this image response (Image recitation block).', 'upstream_image_blocked')
    if result.get('error'):
        raise GatewayError(502, 'AI Studio returned no supported, ready image within its byte limit.', 'invalid_upstream_image')
    return result


def decode_image_output(uri):
    if not isinstance(uri, str) or len(uri) > 4*((MAX_GENERATED_IMAGE_BYTES+2)//3)+100:
        raise GatewayError(502, 'AI Studio image exceeds its byte limit.', 'invalid_upstream_image')
    match = re.fullmatch(r'data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)', uri)
    if not match:
        raise GatewayError(502, 'AI Studio returned an unsupported image encoding.', 'invalid_upstream_image')
    try:
        data = base64.b64decode(match[2], validate=True)
        fmt, dimensions = validate_image_bytes(data, match[1], max_bytes=MAX_GENERATED_IMAGE_BYTES)
    except (GatewayError, ValueError, binascii.Error):
        raise GatewayError(502, 'AI Studio returned an invalid output image.', 'invalid_upstream_image') from None
    return data, fmt, dimensions
