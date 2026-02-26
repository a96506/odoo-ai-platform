"""WebSocket endpoint for real-time dashboard updates via Redis pub/sub."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import structlog

from app.config import get_settings

logger = structlog.get_logger()

router = APIRouter(tags=["websocket"])

DASHBOARD_CHANNEL = "dashboard_events"


class ConnectionManager:
    """Manage active WebSocket connections with optional role filtering."""

    def __init__(self):
        self.active: list[tuple[WebSocket, str | None]] = []

    async def connect(self, ws: WebSocket, role: str | None = None):
        await ws.accept()
        self.active.append((ws, role))
        logger.info("ws_connected", role=role, total=len(self.active))

    def disconnect(self, ws: WebSocket):
        self.active = [(w, r) for w, r in self.active if w is not ws]
        logger.info("ws_disconnected", total=len(self.active))

    async def broadcast(self, message: dict):
        msg_role = message.get("role")
        dead: list[WebSocket] = []
        for ws, role in self.active:
            if msg_role and role and msg_role != role:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def count(self) -> int:
        return len(self.active)


manager = ConnectionManager()


def _get_redis():
    """Create a Redis client for pub/sub. Returns None if unavailable."""
    try:
        import redis
        settings = get_settings()
        return redis.Redis.from_url(settings.redis_url, decode_responses=True)
    except Exception:
        return None


async def _redis_listener():
    """Background task: subscribe to Redis pub/sub and forward to WebSocket clients."""
    r = _get_redis()
    if not r:
        logger.warning("redis_pubsub_unavailable")
        return

    pubsub = r.pubsub()
    pubsub.subscribe(DASHBOARD_CHANNEL)
    logger.info("redis_pubsub_subscribed", channel=DASHBOARD_CHANNEL)

    try:
        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    if "timestamp" not in data:
                        data["timestamp"] = datetime.utcnow().isoformat()
                    await manager.broadcast(data)
                except (json.JSONDecodeError, TypeError):
                    pass
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        pubsub.unsubscribe(DASHBOARD_CHANNEL)
        pubsub.close()
        r.close()
    except Exception as exc:
        logger.error("redis_pubsub_error", error=str(exc))


_listener_task: asyncio.Task | None = None


def _ensure_listener():
    """Start the Redis listener if not already running."""
    global _listener_task
    if _listener_task is None or _listener_task.done():
        loop = asyncio.get_event_loop()
        _listener_task = loop.create_task(_redis_listener())


@router.websocket("/ws/dashboard")
async def websocket_dashboard(ws: WebSocket, role: str | None = None):
    """WebSocket endpoint for real-time dashboard events.

    Query params:
        role: Optional filter — only receive events targeted at this role.
    """
    _ensure_listener()
    await manager.connect(ws, role)
    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
            except (json.JSONDecodeError, TypeError):
                pass
    except WebSocketDisconnect:
        manager.disconnect(ws)


def publish_event(event_type: str, data: dict, role: str | None = None):
    """Publish an event to the dashboard_events Redis channel.

    Called from Celery tasks or anywhere in the backend.
    """
    r = _get_redis()
    if not r:
        return

    message = {
        "type": event_type,
        "data": data,
        "timestamp": datetime.utcnow().isoformat(),
    }
    if role:
        message["role"] = role

    try:
        r.publish(DASHBOARD_CHANNEL, json.dumps(message))
    except Exception as exc:
        logger.warning("publish_event_failed", error=str(exc))
    finally:
        r.close()
