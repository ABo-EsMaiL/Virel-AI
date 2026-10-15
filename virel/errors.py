"""Client-readable gateway failures shared by HTTP adapters."""
from fastapi import HTTPException
from fastapi.responses import JSONResponse


class GatewayError(HTTPException):
    def __init__(self, status_code, message, code, *, param=None, supported_values=None):
        super().__init__(status_code, detail={"message": message, "type": "rate_limit_error" if status_code == 429 else ("server_error" if status_code >= 500 else "invalid_request_error"), "code": code})
        if param is not None:
            self.detail["param"] = param
        if supported_values is not None:
            self.detail["supported_values"] = supported_values


def provider_error(exc):
    detail = exc.detail
    if isinstance(detail, dict):
        return {**{key: detail[key] for key in ("param", "supported_values") if key in detail},
                "message": str(detail.get("message") or detail.get("error") or "Request failed."),
                "type": detail.get("type", "invalid_request_error"),
                "code": detail.get("code") or detail.get("type") or "request_error"}
    return {"message": str(detail), "type": "invalid_request_error", "code": "request_error"}


async def http_error_handler(request, exc):
    return JSONResponse({"error": provider_error(exc)}, status_code=exc.status_code, headers=exc.headers)


async def validation_error_handler(request, exc):
    return JSONResponse({"error": {"message": "Invalid request body.", "type": "invalid_request_error", "code": "validation_error"}}, status_code=422)


async def rate_limit_handler(request, exc):
    return JSONResponse({"error": {"message": "Gateway rate limit exceeded.", "type": "rate_limit_error", "code": "rate_limit_exceeded"}}, status_code=429)
