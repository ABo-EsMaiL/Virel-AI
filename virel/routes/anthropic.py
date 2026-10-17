"""Native Messages endpoint; no client tools execute here."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from ..anthropic import messages_response, native_error
from ..auth import verify_native_key
from ..config import RATE_LIMIT
from ..errors import GatewayError
from ..runtime import limiter, _get_semaphore
router=APIRouter()

@router.post("/v1/messages",dependencies=[Depends(verify_native_key)])
@limiter.limit(RATE_LIMIT)
async def messages(request:Request):
    if request.headers.get("anthropic-version","2023-06-01") != "2023-06-01":
        raise GatewayError(400,"Unsupported anthropic-version; use 2023-06-01.","unsupported_parameter")
    return await messages_response(await request.json(),_get_semaphore(),
        request.headers.get("authorization") or "Bearer "+request.headers.get("x-api-key",""))

@router.post("/v1/messages/count_tokens",dependencies=[Depends(verify_native_key)])
async def count_tokens(request:Request):
    error=GatewayError(501,"Exact token counting before browser generation is unavailable.","unsupported_capability")
    return JSONResponse(native_error(error),status_code=501)
