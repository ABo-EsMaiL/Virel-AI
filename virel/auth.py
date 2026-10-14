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
