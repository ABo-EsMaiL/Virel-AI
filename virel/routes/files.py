"""Native Files endpoints for validated, expiring PDF uploads."""
import asyncio
from fastapi import APIRouter, Depends, File, Form, UploadFile, Request
from fastapi.responses import Response
from ..auth import verify_api_key
from ..files import MAX_PDF_BYTES, require_file_key, save_uploaded, list_stored, read_stored, delete_stored
from ..config import RATE_LIMIT
from ..runtime import limiter
from ..errors import GatewayError

router = APIRouter(prefix='/v1/files', dependencies=[Depends(verify_api_key), Depends(require_file_key)])


@router.post('')
@limiter.limit(RATE_LIMIT)
async def upload_file(request: Request, file: UploadFile = File(...), purpose: str = Form('user_data')):
    try:
        if file.content_type not in ('application/pdf', 'application/octet-stream'):
            raise GatewayError(400, 'Only PDF uploads are supported.', 'invalid_file')
        data = await file.read(MAX_PDF_BYTES+1)
        return await save_uploaded(data, file.filename, purpose)
    finally:
        await file.close()


@router.get('')
async def list_files():
    return {'object': 'list', 'data': await asyncio.to_thread(list_stored), 'has_more': False}


@router.get('/{file_id}')
async def retrieve_file(file_id: str):
    item, _ = await asyncio.to_thread(read_stored, file_id)
    return item


@router.get('/{file_id}/content')
async def file_content(file_id: str):
    _, data = await asyncio.to_thread(read_stored, file_id)
    return Response(data, media_type='application/pdf', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@router.delete('/{file_id}')
async def delete_file(file_id: str):
    return await asyncio.to_thread(delete_stored, file_id)
