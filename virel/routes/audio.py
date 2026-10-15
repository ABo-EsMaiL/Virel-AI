"""Native transcription/English-translation protocols backed by AI Studio."""
import re
import uuid
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.datastructures import UploadFile
from ..auth import verify_api_key
from ..audio import prepared_audio, MAX_AUDIO_BYTES
from ..config import DEFAULT_MODEL, RATE_LIMIT
from ..errors import GatewayError
from ..generation import checked_stream, require_ready, usage_headers
from ..runtime import browser_manager, limiter, _get_semaphore

router = APIRouter(prefix='/v1/audio', dependencies=[Depends(verify_api_key)])


async def audio_response(request, translate):
    sem = _get_semaphore()
    if sem.locked():
        raise GatewayError(429, 'Browser is processing another request.', 'concurrency_limit')
    require_ready()
    async with request.form(max_files=1, max_fields=8) as form:
        allowed = {'file', 'model', 'response_format', 'temperature'} | (set() if translate else {'language'})
        if any(key not in allowed or len(form.getlist(key)) != 1 for key in form):
            raise GatewayError(400, 'Unsupported or repeated audio parameters.', 'unsupported_parameter')
        upload = form.get('file')
        model = form.get('model')
        if not isinstance(upload, UploadFile) or not isinstance(model, str) or len(model) > 128 or not re.fullmatch(r'[A-Za-z0-9._:/-]+', model):
            raise GatewayError(400, 'Audio requires a file and model.', 'invalid_request')
        response_format = form.get('response_format', 'json')
        if response_format not in ('json', 'text'):
            raise GatewayError(400, 'Only JSON or text audio responses are supported.', 'unsupported_parameter')
        if 'temperature' in form:
            # Native n8n omits its default zero; explicit controls need a real UI mapping.
            raise GatewayError(400, 'Audio temperature control is not implemented.', 'unsupported_parameter')
        language = form.get('language')
        if language is not None and (not isinstance(language, str) or not re.fullmatch('[a-z]{2}', language)):
            raise GatewayError(400, 'Language must be a two-letter lowercase ISO code.', 'invalid_request')
        actual_model = DEFAULT_MODEL if model == 'whisper-1' else model
        task = 'Translate the audible speech into English.' if translate else 'Transcribe the audible speech in its original language. Do not translate.'
        if language:
            task += ' The caller supplied this source-language hint: '+language+'.'
        prompt = task+' Use only the attached audio. Return only the resulting text, without explanations, timestamps or Markdown. If there is no audible speech, return exactly [NO_SPEECH].'
        data = await upload.read(MAX_AUDIO_BYTES+1)
        request_id = 'audio_'+uuid.uuid4().hex[:16]
        async with sem:
            async with browser_manager.lock:
                async with prepared_audio(data, upload.filename, upload.content_type) as path:
                    text = ''
                    async for item in checked_stream(prompt, request_id, model_name=actual_model, attachments=[path]):
                        text = item['text'] if isinstance(item, dict) else text+item
                text = '' if text.strip() == '[NO_SPEECH]' else text.strip()
                active_model = browser_manager.active_model or actual_model
                headers = usage_headers(request_id)
                headers.update({'X-Virel-Requested-Model': model, 'X-Virel-Actual-Model': active_model})
                if response_format == 'text':
                    return PlainTextResponse(text, headers=headers)
                return JSONResponse({'text': text, 'model': active_model, 'requested_model': model,
                    'usage': browser_manager.last_usage.responses() if browser_manager.last_usage else None}, headers=headers)


@router.post('/transcriptions')
@limiter.limit(RATE_LIMIT)
async def transcriptions(request: Request):
    return await audio_response(request, False)


@router.post('/translations')
@limiter.limit(RATE_LIMIT)
async def translations(request: Request):
    return await audio_response(request, True)
