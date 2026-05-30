"""Bearer token auth for HTTP and WebSocket."""

from __future__ import annotations

from fastapi import Header, HTTPException, WebSocket

from config import VOICE_API_KEY


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        return ''
    parts = authorization.split(' ', 1)
    if len(parts) == 2 and parts[0].lower() == 'bearer':
        return parts[1].strip()
    return authorization.strip()


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    if not VOICE_API_KEY:
        return
    token = _extract_bearer(authorization)
    if token != VOICE_API_KEY:
        raise HTTPException(status_code=401, detail='Invalid or missing API key.')


async def require_ws_api_key(websocket: WebSocket) -> bool:
    if not VOICE_API_KEY:
        return True
    auth = websocket.headers.get('authorization') or ''
    token = _extract_bearer(auth)
    if token != VOICE_API_KEY:
        await websocket.close(code=4401, reason='Unauthorized')
        return False
    return True
