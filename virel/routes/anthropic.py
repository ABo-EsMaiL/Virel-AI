"""Native Messages endpoint; no client tools execute here."""
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from ..anthropic import messages_response, native_error
from ..auth import verify_native_key
from ..config import RATE_LIMIT
from ..errors import GatewayError
from ..runtime import limiter, _get_semaphore
router=APIRouter()
desktop_router=APIRouter(prefix="/claude")

@desktop_router.post("/v1/messages",dependencies=[Depends(verify_native_key)])
@router.post("/v1/messages",dependencies=[Depends(verify_native_key)])
@limiter.limit(RATE_LIMIT)
async def messages(request:Request):
    if request.headers.get("anthropic-version","2023-06-01") != "2023-06-01":
        raise GatewayError(400,"Unsupported anthropic-version; use 2023-06-01.","unsupported_parameter")
    return await messages_response(await request.json(),_get_semaphore(),
        request.headers.get("authorization") or "Bearer "+request.headers.get("x-api-key",""),
        desktop=request.url.path.startswith("/claude/"))

@desktop_router.post("/v1/messages/count_tokens",dependencies=[Depends(verify_native_key)])
@router.post("/v1/messages/count_tokens",dependencies=[Depends(verify_native_key)])
async def count_tokens(request:Request):
    error=GatewayError(501,"Exact token counting before browser generation is unavailable.","unsupported_capability")
    return JSONResponse(native_error(error),status_code=501)


@desktop_router.get("/v1/models",dependencies=[Depends(verify_native_key)])
async def desktop_models(refresh:bool=False, limit:int=Query(1000,ge=1,le=1000), after_id:str|None=None):
    from .system import list_models
    from ..models import desktop_aliases
    from ..runtime import browser_manager
    catalog = await list_models(refresh)
    aliases = {original:alias for alias,original in desktop_aliases(browser_manager.model_catalog).items()}
    records = [
        {**item, "id":aliases[item["id"]], "type":"model",
         "display_name":item["display_name"].replace("Gemini","Claude") + " (Virel alias)",
         "created_at":"1970-01-01T00:00:00Z",
         "virel":{**item["virel"], "compatibility_alias":True, "requested_ui_model":item["id"],
                  "actual_model":item["virel"].get("resolved_id") or item["id"],
                  "actual_display_name":item["display_name"]}}
        for item in catalog["data"]
    ]
    if after_id is not None:
        index = next((i for i,item in enumerate(records) if item["id"] == after_id), None)
        if index is None:
            raise GatewayError(400,"Unknown model pagination cursor.","invalid_request")
        records = records[index+1:]
    page = records[:limit]
    return {"data":page, "has_more":len(records)>limit,
            "first_id":page[0]["id"] if page else None, "last_id":page[-1]["id"] if page else None}
