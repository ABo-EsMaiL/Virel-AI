"""Native image generation/edit protocols using actual AI Studio image output."""
import asyncio
import base64
import json
import time
import uuid
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile
from ..auth import verify_api_key
from ..config import RATE_LIMIT
from ..errors import GatewayError
from ..generation import checked_stream, require_ready, usage_headers, response_model
from ..image_output import image_options, encode_image_output
from ..images import MAX_IMAGE_BYTES, MAX_IMAGES
from ..runtime import browser_manager, limiter, _get_semaphore

router = APIRouter(prefix='/v1/images', dependencies=[Depends(verify_api_key)])


async def run_image(body, sources):
    requested, model, prompt, size, options = image_options(body)
    sem = _get_semaphore()
    if sem.locked():
        raise GatewayError(429, 'Browser is processing another request.', 'concurrency_limit')
    require_ready()
    request_id = 'image_'+uuid.uuid4().hex[:16]
    async with sem:
        async with browser_manager.lock:
            uri = None
            async for item in checked_stream(prompt, request_id, model_name=model, images=sources, output_kind='image', image_size=size, image_settings=options, temperature=options.get('temperature'), reasoning_effort=options.get('reasoning_effort')):
                if isinstance(item, dict) and item.get('image'):
                    uri = item['image']
            data, dimensions, encoding = await asyncio.to_thread(encode_image_output, uri, options['output_format'], options.get('output_compression'))
            if size == '1024x1024' and dimensions != (1024, 1024):
                raise GatewayError(502, 'AI Studio image did not match the requested exact dimensions.', 'upstream_image_size_mismatch', param='size')
            actual = response_model(model)
            browser_manager.generated_models.add(actual)
            headers = usage_headers(request_id)
            headers.update({'X-Virel-Requested-Model': requested, 'X-Virel-Actual-Model': actual})
            return JSONResponse({'created': int(time.time()), 'model': actual, 'requested_model': requested,
                'data': [{'b64_json': base64.b64encode(data).decode('ascii')}], 'encoding': encoding,
                'usage': browser_manager.last_usage.responses() if browser_manager.last_usage else None}, headers=headers)


@router.post('/generations')
@limiter.limit(RATE_LIMIT)
async def generations(request: Request):
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise GatewayError(400, 'Expected a valid JSON image request.', 'invalid_request') from None
    return await run_image(body, [])


@router.post('/edits')
@limiter.limit(RATE_LIMIT)
async def edits(request: Request):
    async with request.form(max_files=MAX_IMAGES, max_fields=24) as form:
        fields = [name for name in ('image', 'image[]') if name in form]
        if len(fields) != 1:
            raise GatewayError(400, 'Supply image or image[] uploads.', 'invalid_image')
        field = fields[0]
        if any(len(form.getlist(key)) != 1 for key in form if key != field):
            raise GatewayError(400, 'Repeated image parameters are unsupported.', 'unsupported_parameter')
        body = {key: value for key, value in form.items() if key != field}
        image_options(body)
        require_ready()
        if _get_semaphore().locked():
            raise GatewayError(429, 'Browser is processing another request.', 'concurrency_limit')
        uploads = form.getlist(field)
        if not uploads or len(uploads) > MAX_IMAGES or any(not isinstance(upload, UploadFile) for upload in uploads):
            raise GatewayError(400, 'Supply supported binary image uploads.', 'invalid_image')
        sources = []
        for upload in uploads:
            if upload.content_type not in ('image/png', 'image/jpeg', 'image/webp'):
                raise GatewayError(400, 'Edit image must declare PNG, JPEG or WebP MIME.', 'invalid_image')
            data = await upload.read(MAX_IMAGE_BYTES+1)
            if len(data) > MAX_IMAGE_BYTES:
                raise GatewayError(413, 'Edit image exceeds its byte limit.', 'image_too_large')
            sources.append('data:'+upload.content_type+';base64,'+base64.b64encode(data).decode('ascii'))
        return await run_image(body, sources)
