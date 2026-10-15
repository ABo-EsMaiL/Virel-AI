"""Observed speech editor, strict native options and private encoding lifetime."""
import asyncio
import base64
import binascii
import math
from pathlib import Path
import re
import sys
import tempfile
import time
from playwright.async_api import Error as PlaywrightError
from .config import (BASE_DIR, TARGET_URL, TEMP_UPLOADS_DIR, DEFAULT_SPEECH_MODEL,
    DEFAULT_SPEECH_VOICE, MAX_GENERATED_AUDIO_BYTES, MAX_SPEECH_CHARACTERS, MAX_SPEECH_SECONDS)
from .errors import GatewayError

VOICE_SELECTORS = {'echo':'Bodi', 'fable':'Koda', 'nova':'Lumi', 'onyx':'Mako', 'shimmer':'Sola'}
MIMES = {'auto':'audio/wav', 'wav':'audio/wav', 'mp3':'audio/mpeg', 'opus':'audio/ogg',
    'aac':'audio/aac', 'flac':'audio/flac', 'pcm':'audio/pcm'}
SPEECH_TEXT = 'textarea[aria-label="Speech block text"]'
SPEECH_RUN = 'ms-audio-footer button.ctrl-enter-submits'


def speech_options(body):
    if not isinstance(body, dict):
        raise GatewayError(400, 'Expected a JSON speech request.', 'invalid_request')
    unknown = sorted(set(body) - {'model', 'input', 'voice', 'response_format', 'speed'})
    if unknown:
        raise GatewayError(400, 'This speech parameter is not implemented by the website adapter.',
            'unsupported_parameter', param=unknown[0])
    text = body.get('input')
    if not isinstance(text, str) or not text.strip():
        raise GatewayError(400, 'Speech input must be nonempty text.', 'invalid_request', param='input')
    if len(text) > MAX_SPEECH_CHARACTERS:
        raise GatewayError(413, 'Speech text exceeds the configured character limit.', 'speech_input_too_large', param='input')
    requested = body.get('model', DEFAULT_SPEECH_MODEL)
    if not isinstance(requested, str) or not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,127}', requested):
        raise GatewayError(400, 'Use an observed speech model ID.', 'invalid_request', param='model')
    requested_voice = body.get('voice', DEFAULT_SPEECH_VOICE)
    if not isinstance(requested_voice, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,63}', requested_voice):
        raise GatewayError(400, 'Use an actual voice name or a documented native selector.', 'invalid_request', param='voice')
    fmt = body.get('response_format', 'auto')
    if fmt not in tuple(MIMES):
        raise GatewayError(400, 'Unsupported audio file format.', 'unsupported_parameter', param='response_format', supported_values=list(MIMES))
    speed = body.get('speed', 1)
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed) or not .25 <= speed <= 4:
        raise GatewayError(400, 'Speed must be a finite number from 0.25 to 4.', 'invalid_request', param='speed')
    return {'text':text, 'requested_model':requested,
        'model':DEFAULT_SPEECH_MODEL if requested in ('tts-1', 'tts-1-hd') else requested,
        'requested_voice':requested_voice,
        'voice':DEFAULT_SPEECH_VOICE if requested_voice == 'alloy' else VOICE_SELECTORS.get(requested_voice, requested_voice),
        'format':fmt, 'speed':speed}


READ_SPEECH_OUTPUT = r"""async ({includeData,maxBytes}) => {
    const root=document.querySelector('ms-speech-prompt');
    const footer=root?.querySelector('ms-audio-footer');
    const errors=Array.from(document.querySelectorAll('mat-snack-bar-container,[role=alert],ms-speech-prompt .error-message'))
        .filter(e=>e.getClientRects().length).map(e=>e.innerText||'').join(' ');
    if (/quota exceeded|daily limit of requests|reached your rate limit|resource.exhausted/i.test(errors)) return {error:'quota'};
    if (/API key (?:is )?required|select an API key|billing required/i.test(errors)) return {error:'paid'};
    if (/failed to generate|generation failed|blocked|safety|recitation/i.test(errors)) return {error:'generation'};
    const button=footer?.querySelector('button.ctrl-enter-submits');
    const running=/\b(?:Stop|Cancel)\b/i.test(button?.innerText||'');
    const audios=Array.from(footer?.querySelectorAll('audio')||[]);
    if(audios.length>1) return {error:'multiple'};
    const audio=audios[0], src=audio?.currentSrc||audio?.getAttribute('src')||'';
    const ready=Boolean(button) && /\bRun\b/i.test(button.innerText||'') && !running && audios.length===1 && audio.readyState>=2 && Number.isFinite(audio.duration) && audio.duration>0.1;
    const result={running,ready,identity:src.length+':'+src.slice(-96)+':'+audio?.duration};
    if(!includeData || !ready) return result;
    const maxEncoded=4*Math.ceil(maxBytes/3)+100;
    if(/^data:audio\/(?:wav|x-wav);base64,/.test(src)) return src.length<=maxEncoded?{...result,data:src}:{error:'too_large'};
    if(location.origin!=='https://aistudio.google.com'||!src.startsWith('blob:'+location.origin+'/')) return {error:'source'};
    const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),15000);
    try{
        const response=await fetch(src,{signal:abort.signal});
        if(!response.ok||Number(response.headers.get('content-length'))>maxBytes||!response.body) return {error:'asset'};
        const reader=response.body.getReader(),chunks=[];let size=0;
        while(true){const {value,done}=await reader.read();if(done)break;size+=value.byteLength;
            if(size>maxBytes){await reader.cancel();return {error:'too_large'};}chunks.push(value);}
        const blob=new Blob(chunks,{type:'audio/wav'});
        const data=await new Promise((resolve,reject)=>{const file=new FileReader();file.onload=()=>resolve(file.result);file.onerror=reject;file.readAsDataURL(blob);});
        return data.length<=maxEncoded?{...result,data}:{error:'too_large'};
    }catch{return {error:'asset'};}finally{clearTimeout(timer);}
}"""


async def read_speech_output(page, include_data=False):
    result = await page.evaluate(READ_SPEECH_OUTPUT, {'includeData':include_data, 'maxBytes':MAX_GENERATED_AUDIO_BYTES})
    code = result.get('error')
    if code == 'quota':
        raise GatewayError(429, 'AI Studio speech quota or rate limit reached. No automatic retry was made.', 'upstream_rate_limit')
    if code == 'paid':
        raise GatewayError(503, 'AI Studio requires paid/API-key access for this speech request.', 'model_unavailable')
    if code:
        raise GatewayError(413 if code == 'too_large' else 502, 'AI Studio did not return a supported current speech asset.',
            'upstream_audio_too_large' if code == 'too_large' else 'upstream_audio_'+code)
    return result


async def select_voice(page, voice):
    chip = page.locator('button.voice-chip')
    if await chip.count() != 1:
        raise GatewayError(503, 'Expected exactly one speech speaker.', 'speech_ui_unavailable')
    def matches(value):
        return re.search(r' - '+re.escape(voice)+r'(?:\n|$)', value) is not None
    if matches(await chip.inner_text()):
        return
    await page.get_by_role('button', name='Open voice settings', exact=True).click(timeout=6000)
    try:
        search = page.locator('input[aria-label="Search voices"]:visible')
        await search.fill(voice, timeout=6000)
        choices = page.locator('button.voice-card-content').filter(has=page.locator('.voice-name').filter(has_text=re.compile('^'+re.escape(voice)+'$')))
        try:
            await choices.first.wait_for(state='visible', timeout=4000)
        except PlaywrightError:
            raise GatewayError(400, 'Voice was not available in the current AI Studio library.', 'unsupported_voice', param='voice') from None
        if await choices.count() != 1 or not await choices.is_enabled() or await choices.get_attribute('aria-disabled') == 'true':
            raise GatewayError(400, 'Voice is unavailable or ambiguous.', 'unsupported_voice', param='voice')
        card = choices.locator('..')
        if await card.locator('ms-badge').filter(has_text=re.compile('Paid',re.I)).count():
            raise GatewayError(400, 'Voice requires paid access.', 'unsupported_voice', param='voice')
        await choices.click(timeout=6000)
        if not matches(await chip.inner_text()):
            raise GatewayError(503, 'Selected speech voice could not be verified.', 'settings_unavailable', param='voice')
    finally:
        await page.keyboard.press('Escape')


async def generate_in_speech_page(manager, text, model, voice):
    page = manager.page
    completed = False
    try:
        if not await manager.reset_chat_if_needed(model, output_kind='speech') or not manager.model_verified:
            raise GatewayError(503, 'Could not start a fresh verified speech model.', 'model_unavailable')
        create = page.locator('mat-card.create-dialog-card')
        await create.wait_for(state='visible', timeout=8000)
        await create.click(timeout=6000)
        editor = page.locator(SPEECH_TEXT)
        await editor.first.wait_for(state='visible', timeout=8000)
        if await editor.count() != 1 or await editor.input_value() or await page.locator('ms-audio-footer audio').count():
            raise GatewayError(503, 'Fresh speech dialog could not be verified.', 'browser_not_ready')
        await select_voice(page, voice)
        await editor.fill(text)
        await editor.press('Space')
        await editor.press('Backspace')
        if await editor.input_value() != text:
            raise GatewayError(503, 'Speech transcript could not be verified.', 'speech_ui_unavailable')
        run = page.locator(SPEECH_RUN)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if await run.is_enabled() and await run.get_attribute('aria-disabled') != 'true':
                break
            await asyncio.sleep(.2)
        else:
            raise GatewayError(503, 'Speech Run did not become ready.', 'speech_ui_unavailable')
        await run.click(timeout=6000)
        start = time.monotonic()
        previous = None
        stable = start
        while time.monotonic() - start < 1200:
            state = await read_speech_output(page)
            signature = (state.get('identity'), state.get('ready'), state.get('running'))
            if signature != previous:
                previous, stable = signature, time.monotonic()
            # The completed Run can precede the final audio DOM update; 40ms silence is a placeholder.
            if state.get('ready') and time.monotonic() - stable >= 4:
                final = await read_speech_output(page, True)
                if final.get('identity') == state['identity'] and final.get('data'):
                    uri = final['data']
                    if not re.fullmatch(r'data:audio/(?:wav|x-wav);base64,[A-Za-z0-9+/=]+', uri):
                        raise GatewayError(502, 'Invalid generated speech encoding.', 'upstream_audio_asset')
                    try:
                        data = base64.b64decode(uri.split(',',1)[1], validate=True)
                    except (ValueError, binascii.Error):
                        raise GatewayError(502, 'Invalid generated speech bytes.', 'upstream_audio_asset') from None
                    if len(data) > MAX_GENERATED_AUDIO_BYTES:
                        raise GatewayError(413, 'Generated speech exceeds the byte limit.', 'upstream_audio_too_large')
                    completed = True
                    return data
            if time.monotonic() - start > 180 and not state.get('running') and not state.get('ready'):
                raise GatewayError(502, 'AI Studio returned no complete speech audio.', 'upstream_no_audio')
            await asyncio.sleep(.25)
        raise GatewayError(504, 'AI Studio speech generation timed out.', 'upstream_timeout')
    except GatewayError:
        raise
    except PlaywrightError:
        raise GatewayError(503, 'The AI Studio speech interface is unavailable.', 'speech_ui_unavailable') from None
    finally:
        if not completed and page and not page.is_closed():
            try:
                await page.goto(TARGET_URL, timeout=15000, wait_until='domcontentloaded')
            except Exception:
                manager.is_ready = False


async def encode_speech(data, fmt, speed):
    if len(data) > MAX_GENERATED_AUDIO_BYTES:
        raise GatewayError(413, 'Generated audio exceeds the configured byte limit.', 'upstream_audio_too_large')
    Path(TEMP_UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='speech-', dir=TEMP_UPLOADS_DIR) as folder:
        source, target = Path(folder)/'source.wav', Path(folder)/'output.audio'
        source.write_bytes(data)
        process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'virel.speech_encoding',
            str(source), str(target), fmt, str(speed), str(MAX_GENERATED_AUDIO_BYTES), str(MAX_SPEECH_SECONDS),
            cwd=BASE_DIR, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            code = await asyncio.wait_for(process.wait(), timeout=30)
        except (asyncio.TimeoutError, asyncio.CancelledError) as error:
            if process.returncode is None:
                process.kill()
            await process.wait()
            if isinstance(error, asyncio.CancelledError):
                raise
            raise GatewayError(502, 'Speech file processing exceeded its deadline.', 'audio_encoding_failed') from None
        if code:
            raise GatewayError(413 if code == 2 else 502, 'Speech source is invalid or could not be encoded within the limits.',
                'upstream_audio_too_large' if code == 2 else 'audio_encoding_failed')
        if not target.exists() or target.stat().st_size > MAX_GENERATED_AUDIO_BYTES:
            raise GatewayError(502, 'Speech encoder returned an invalid file.', 'audio_encoding_failed')
        return target.read_bytes()
