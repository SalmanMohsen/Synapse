"""
WebSocket endpoint — single persistent connection per client.

Connect flow:
1. Accept the connection.
2. Extract JWT from the ``access_token`` cookie or ``Authorization: Bearer``
   header and validate it (decode + revocation check).  Close 4001 on failure.
3. Load the user and compute their Redis Pub/Sub subscriptions.
4. Subscribe to all relevant Redis channels and forward incoming messages to
   the client until the connection drops.

Clients NEVER send data over WebSocket — all mutations go through REST.
The recv loop exists only to detect the DISCONNECT frame promptly.
"""
import asyncio

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.repository import UserRepository
from app.auth.utils.jwt import decode_token
from app.database import AsyncSessionFactory

from .manager import compute_subscriptions

ws_router = APIRouter(tags=["websocket"])


async def _authenticate(websocket: WebSocket, redis: aioredis.Redis) -> str | None:
    """Return the authenticated user_id or None if auth fails.

    Reads token from the ``access_token`` cookie first; falls back to the
    ``Authorization: Bearer <token>`` header for non-browser clients.
    """
    token: str | None = websocket.cookies.get("access_token")
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()

    if not token:
        return None

    try:
        payload = decode_token(token)
    except ValueError:
        return None

    if payload.type != "access":
        return None

    if await redis.get(f"revoked:{payload.jti}"):
        return None

    return payload.sub


async def _load_subscriptions(user_id: str) -> list[str]:
    """Open a short-lived DB session to compute this user's subscription list."""
    async with AsyncSessionFactory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if user is None:
            return []
        return await compute_subscriptions(session, user_id)


async def _forward_redis_to_ws(pubsub, websocket: WebSocket) -> None:
    """Listen on *pubsub* and forward every message to *websocket*.

    Raises WebSocketDisconnect / ConnectionError when the client drops.
    """
    async for raw in pubsub.listen():
        if raw["type"] == "message":
            await websocket.send_text(raw["data"])


async def _drain_client_frames(websocket: WebSocket) -> None:
    """Receive and discard client frames until a DISCONNECT frame arrives.

    Clients should never send data, but we still need to drain the receive
    channel so that starlette detects the disconnect and propagates it.
    """
    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                return
    except Exception:
        return


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    redis: aioredis.Redis = websocket.app.state.redis

    user_id = await _authenticate(websocket, redis)
    if user_id is None:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    redis_channels = await _load_subscriptions(user_id)
    if not redis_channels:
        # User was deleted between auth and subscription load.
        await websocket.close(code=4001, reason="User not found")
        return

    pubsub = redis.pubsub()
    await pubsub.subscribe(*redis_channels)

    fwd_task = asyncio.create_task(_forward_redis_to_ws(pubsub, websocket))
    disc_task = asyncio.create_task(_drain_client_frames(websocket))

    try:
        _, pending = await asyncio.wait(
            [fwd_task, disc_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, WebSocketDisconnect, Exception):
                pass
    finally:
        await pubsub.unsubscribe(*redis_channels)
        await pubsub.aclose()