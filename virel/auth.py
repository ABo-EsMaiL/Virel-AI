"""Gateway client Bearer authentication; unrelated to Google authentication."""

from typing import Optional
from fastapi import Header, HTTPException
from .config import API_KEY


async def verify_api_key(authorization: Optional[str] = Header(None)):
    if not API_KEY:
        return True

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={"error": "Missing Authorization header. Expected: Bearer <key>", "type": "auth_error"}
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or parts[1] != API_KEY:
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid Gateway API Key", "type": "auth_error"}
        )
    return True


async def verify_native_key(authorization: Optional[str] = Header(None), x_api_key: Optional[str] = Header(None)):
    if x_api_key is not None and authorization is not None and authorization != "Bearer " + x_api_key:
        raise HTTPException(401, detail={"message":"Conflicting gateway credentials.","type":"auth_error"})
    return await verify_api_key(authorization or ("Bearer " + x_api_key if x_api_key else None))
