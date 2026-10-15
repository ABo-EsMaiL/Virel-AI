"""Native image options and bounded current-response image extraction."""
import base64
import binascii
import re
import io
import math
from PIL import Image
from playwright.async_api import Error as PlaywrightError
from .config import DEFAULT_IMAGE_MODEL, MAX_GENERATED_IMAGE_BYTES
from .errors import GatewayError
from .images import validate_image_bytes


def image_option_error(name, message, values=None):
    raise GatewayError(400, f'{name}: {message}', 'unsupported_parameter', param=name, supported_values=values)


def image_options(body):
    if not isinstance(body, dict):
        raise GatewayError(400, 'Expected image options object.', 'invalid_request')
    allowed = {'model', 'prompt', 'n', 'size', 'quality', 'response_format', 'output_format', 'output_compression',
               'aspect_ratio', 'resolution', 'temperature', 'reasoning_effort', 'top_p', 'max_output_tokens', 'background'}
    unknown = sorted(set(body) - allowed)
    if unknown:
        name = unknown[0]
        reason = 'AI Studio has no uploaded pixel-mask control; describe a semantic edit in prompt.' if name == 'mask' else ('AI Studio has no input-fidelity control.' if name == 'input_fidelity' else 'Parameter is not supported by this image adapter.')
        image_option_error(name, reason)
    requested = body.get('model', DEFAULT_IMAGE_MODEL)
    if not isinstance(requested, str) or not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,127}', requested):
        image_option_error('model', 'Use a valid observed image model ID.')
    prompt = body.get('prompt')
    if not isinstance(prompt, str) or not prompt.strip():
        raise GatewayError(400, 'A nonempty image prompt is required.', 'empty_prompt', param='prompt')
    if type(body.get('n', 1)) not in (int, str) or str(body.get('n', 1)) != '1':
        image_option_error('n', 'The browser supports one output per request.', [1])
    for name, default in [('response_format', 'b64_json'), ('quality', 'auto'), ('background', 'auto')]:
        if body.get(name, default) != default:
            reasons = {'response_format':'Use native binary/base64 output; a hosted result URL is not implemented.',
                       'quality':'AI Studio has no equivalent quality tiers. Use resolution/temperature/thinking controls directly.',
                       'background':'AI Studio has no guaranteed alpha/background control. No background removal is performed.'}
            image_option_error(name, reasons[name], [default])
    size = body.get('size', 'auto')
    if size not in ('auto', '1024x1024'):
        image_option_error('size', 'Use aspect_ratio for other shapes; exact dimensions are not emulated by resizing.', ['auto', '1024x1024'])
    options = {'output_format':body.get('output_format', 'auto'), 'aspect_ratio':body.get('aspect_ratio', '1:1' if size == '1024x1024' else 'Auto'), 'resolution':body.get('resolution', '1K')}
    if options['output_format'] not in ('auto', 'png', 'jpeg', 'webp'):
        image_option_error('output_format', 'Choose original bytes or an explicit file conversion.', ['auto','png','jpeg','webp'])
    ratios = ['Auto','1:1','9:16','16:9','3:4','4:3','3:2','2:3','5:4','4:5','21:9','4:1','1:4','8:1','1:8']
    if options['aspect_ratio'] == 'auto':options['aspect_ratio'] = 'Auto'
    if options['aspect_ratio'] not in ratios:image_option_error('aspect_ratio', 'Use an offered ratio; availability is verified on the selected model.', ratios)
    if options['resolution'] not in ('0.5K','1K','2K','4K'):image_option_error('resolution', 'Use an offered resolution; Lite currently exposes only 1K.', ['0.5K','1K','2K','4K'])
    if size == '1024x1024' and (options['aspect_ratio'] != '1:1' or options['resolution'] != '1K'):
        image_option_error('size', '1024x1024 requires aspect_ratio=1:1 and resolution=1K.', ['auto','1024x1024'])
    for name, low, high in [('temperature',0,2), ('top_p',0,1), ('max_output_tokens',1,2147483647), ('output_compression',0,100)]:
        if name not in body:continue
        value = body[name]
        try:
            if isinstance(value,bool) or not isinstance(value,(int,float,str)):raise ValueError
            value = float(value)
            if not math.isfinite(value) or not low <= value <= high:raise ValueError
            if name in ('max_output_tokens','output_compression') and not value.is_integer():raise ValueError
        except (ValueError, OverflowError):
            image_option_error(name, f'Use a finite {"integer" if name in ("max_output_tokens","output_compression") else "number"} from {low} to {high}.')
        options[name] = int(value) if name in ('max_output_tokens','output_compression') else value
    if 'output_compression' in options and options['output_format'] not in ('jpeg','webp'):
        image_option_error('output_compression', 'Compression is a JPEG/WebP encoding quality percentage; select that output_format explicitly.', ['jpeg','webp'])
    if 'reasoning_effort' in body:
        if body['reasoning_effort'] not in ('minimal','low','medium','high'):
            image_option_error('reasoning_effort', 'Use a model-supported effort; Lite exposes minimal/high.', ['minimal','low','medium','high'])
        options['reasoning_effort'] = body['reasoning_effort']
    actual = DEFAULT_IMAGE_MODEL if requested == 'gpt-image-1' else requested
    return requested, actual, prompt, size, options


async def ensure_image_settings(page, size, settings=None):
    try:
        settings = settings or {}
        mode = page.locator('button[role="radio"]').filter(has_text=re.compile(r'Images only')).first
        await mode.wait_for(state='visible', timeout=6000)
        if await mode.get_attribute('aria-checked') != 'true':
            await mode.click()
        if await mode.get_attribute('aria-checked') != 'true':
            raise GatewayError(503, 'AI Studio image output mode could not be verified.', 'settings_unavailable')
        for label, target in [('Aspect ratio', settings.get('aspect_ratio', '1:1' if size == '1024x1024' else 'Auto')), ('Resolution', settings.get('resolution', '1K'))]:
            control = page.locator('mat-select[aria-label="'+label+'"]').first
            await control.wait_for(state='visible', timeout=6000)
            value = control.locator('.mat-mdc-select-min-line').first
            if not await value.count():
                value = control
            if (await value.inner_text()).strip() != target:
                await control.click()
                options = page.locator('mat-option:visible')
                offered = [(await option.inner_text()).strip() for option in await options.all()]
                for option in await options.all():
                    if (await option.inner_text()).strip() == target:
                        await option.click()
                        await options.first.wait_for(state='hidden', timeout=2000)
                        break
                else:
                    await page.keyboard.press('Escape')
                    image_option_error('aspect_ratio' if label == 'Aspect ratio' else 'resolution', 'Setting is unavailable for the selected model.', offered)
            if (await value.inner_text()).strip() != target:
                raise GatewayError(503, 'AI Studio image setting could not be verified.', 'settings_unavailable')

        advanced = page.get_by_role('button', name=re.compile('Advanced settings', re.I)).first
        maximum = page.locator('input[aria-label="Maximum output tokens"]').first
        if await advanced.count() and await advanced.is_visible() and not await maximum.is_visible():
            await advanced.click()
        for name, label, default in [('top_p','Top P',0.95), ('max_output_tokens','Maximum output tokens',65536)]:
            control = page.locator('input[aria-label="'+label+'"]').first
            if not await control.count() or not await control.is_visible() or not await control.is_enabled():
                if name in settings:image_option_error(name, 'Control is unavailable for the selected model.')
                continue
            low = await control.get_attribute('aria-valuemin') or await control.get_attribute('min')
            high = await control.get_attribute('aria-valuemax') or await control.get_attribute('max')
            target = settings.get(name, min(default,float(high)) if high else default)
            if (low is not None and target < float(low)) or (high is not None and target > float(high)):
                image_option_error(name, 'Value is outside the selected model UI range.', [low,high])
            await control.fill(str(target));await control.press('Tab')
            if abs(float(await control.input_value())-target) > 1e-9 or await control.get_attribute('aria-invalid') == 'true':
                raise GatewayError(503, 'AI Studio image numeric setting could not be verified.', 'settings_unavailable', param=name)
    except (PlaywrightError, ValueError):
        raise GatewayError(503, 'AI Studio image settings are unavailable or could not be verified.', 'settings_unavailable') from None


READ_IMAGE_OUTPUT = r"""async ({initial, includeData, maxBytes}) => {
    const turns = Array.from(document.querySelectorAll('ms-chat-turn'));
    const user = t => Boolean(t.querySelector('.user-prompt-container')) || t.getAttribute('data-turn-role') === 'user';
    const model = t => !user(t) && (Boolean(t.querySelector('.model-prompt-container')) || t.getAttribute('data-turn-role') === 'model');
    const models = turns.filter(model);
    const lastUser = turns.findLastIndex(user);
    const current = new Set(models.slice(initial).filter(t => turns.indexOf(t) > lastUser));
    if (Array.from(current).some(t => /you.?ve reached your rate limit|quota exceeded|daily limit of requests/i.test(t.innerText || ''))) return {error:'image_rate_limit'};
    if (Array.from(current).some(t => /\bImage recitation block\b/i.test(t.innerText || ''))) return {error:'image_recitation_block'};
    if (Array.from(current).some(t => /\bImage (?:safety|prohibited content) block\b|\bIMAGE_(?:SAFETY|PROHIBITED_CONTENT)\b/i.test(t.innerText || ''))) return {error:'image_safety_block'};
    const images = Array.from(current).flatMap(t => Array.from(t.querySelectorAll('ms-image-chunk .image-container img')))
        .filter(e => !e.closest('ms-thought-chunk,.thought-activity-host,ms-grounding-chip,ms-citation-chunk') && e.getClientRects().length);
    const ready = images.length > 0 && images.every(e => e.complete && e.naturalWidth > 0 && e.naturalHeight > 0);
    const result = {count:images.length, ready, broken:images.some(e=>e.complete && (e.currentSrc || e.getAttribute('src')) && !e.naturalWidth),
        identity:images.map(e=>`${(e.currentSrc||e.src).length}:${e.naturalWidth}x${e.naturalHeight}:${e.complete}`).join('|')};
    if (!includeData) return result;
    if (images.length > 1) return {error:'multiple_images'};
    if (!ready) return {error:'missing_image'};
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
    if result.get('error') == 'image_rate_limit':
        raise GatewayError(429, 'AI Studio image quota or rate limit reached. Wait for the provider reset; no automatic retry was made.', 'upstream_rate_limit')
    if result.get('error') == 'image_safety_block':
        raise GatewayError(502, 'AI Studio blocked this image response for safety.', 'upstream_image_safety')
    if result.get('error') == 'image_recitation_block':
        raise GatewayError(502, 'AI Studio blocked this image response (Image recitation block).', 'upstream_image_blocked')
    failures = {
        'missing_image':('AI Studio completed without a ready image.', 'upstream_no_image'),
        'multiple_images':('AI Studio returned multiple images for a single-image request.', 'upstream_multiple_images'),
        'image_too_large':('AI Studio output image exceeds the configured byte limit.', 'upstream_image_too_large'),
        'unsupported_asset':('AI Studio returned an unsupported image source; external authenticated downloads are disabled.', 'upstream_image_source_unsupported'),
        'invalid_asset':('AI Studio original image download failed.', 'upstream_image_download_failed')}
    if result.get('error'):
        message, code = failures.get(result['error'], ('AI Studio returned an invalid image.', 'invalid_upstream_image'))
        raise GatewayError(502, message, code)
    return result


def decode_image_output(uri):
    if not isinstance(uri, str):
        raise GatewayError(502, 'AI Studio completed without an output image.', 'upstream_no_image')
    if len(uri) > 4*((MAX_GENERATED_IMAGE_BYTES+2)//3)+100:
        raise GatewayError(502, 'AI Studio image exceeds its byte limit.', 'upstream_image_too_large')
    match = re.fullmatch(r'data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)', uri)
    if not match:
        raise GatewayError(502, 'AI Studio returned an unsupported image encoding.', 'invalid_upstream_image')
    try:
        data = base64.b64decode(match[2], validate=True)
        fmt, dimensions = validate_image_bytes(data, match[1], max_bytes=MAX_GENERATED_IMAGE_BYTES)
    except (GatewayError, ValueError, binascii.Error):
        raise GatewayError(502, 'AI Studio returned an invalid output image.', 'invalid_upstream_image') from None
    return data, fmt, dimensions


def encode_image_output(uri, output_format='auto', compression=None):
    data, original, dimensions = decode_image_output(uri)
    target = original if output_format == 'auto' else {'png':'PNG','jpeg':'JPEG','webp':'WEBP'}[output_format]
    converted = target != original or compression is not None
    flattened = False
    if converted:
        try:
            with Image.open(io.BytesIO(data)) as image:
                if target == 'JPEG' and image.mode not in ('RGB','L'):
                    rgba = image.convert('RGBA')
                    image = Image.new('RGB', rgba.size, 'white')
                    image.paste(rgba, mask=rgba.getchannel('A'))
                    flattened = rgba.getchannel('A').getextrema()[0] < 255
                output = io.BytesIO()
                encoding_options = {}
                if target in ('JPEG','WEBP'):
                    encoding_options['quality'] = compression if compression is not None else 100
                if target == 'JPEG':encoding_options['subsampling'] = 0
                if target == 'WEBP' and compression in (None,100):encoding_options['lossless'] = True
                image.save(output,format=target,**encoding_options)
                data = output.getvalue()
        except (OSError, ValueError):
            raise GatewayError(502, 'The requested image encoding failed.', 'output_image_encoding_failed') from None
        try:validate_image_bytes(data, max_bytes=MAX_GENERATED_IMAGE_BYTES)
        except GatewayError:
            raise GatewayError(502, 'Converted image exceeds the configured image limits.', 'output_image_too_large') from None
    metadata = {'original_format':original.lower(),'output_format':target.lower(),'converted':converted}
    if flattened:metadata['alpha_background']='white'
    return data, dimensions, metadata
