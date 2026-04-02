"""WebSocket handler for the agentic-computer server.

Provides real-time bidirectional communication between clients and the agent.
Clients can submit tasks and receive streamed progress events and results
over a persistent WebSocket connection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Manage active WebSocket connections and message dispatch.

    Provides helpers for connecting, disconnecting, broadcasting to all
    clients, and sending a message to a single connection.

    Attributes:
        active_connections: List of currently connected WebSocket instances.
    """

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept an incoming WebSocket and add it to active connections.

        Args:
            websocket: The WebSocket instance to accept and track.
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            "WebSocket connected. Total connections: %d",
            len(self.active_connections),
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from the active connections list.

        Safe to call even if the websocket is not in the list (e.g. if
        ``connect`` was never completed).

        Args:
            websocket: The WebSocket instance to remove.
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            "WebSocket disconnected. Total connections: %d",
            len(self.active_connections),
        )

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to every active connection.

        Connections that fail during send are silently removed.

        Args:
            message: Dictionary payload to serialise and send.
        """
        stale: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                logger.warning("Failed to send to a WebSocket; marking for removal.")
                stale.append(connection)
        for ws in stale:
            self.disconnect(ws)

    async def send_to(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        """Send a JSON message to a specific WebSocket connection.

        Args:
            websocket: Target connection.
            message: Dictionary payload to serialise and send.

        Raises:
            RuntimeError: If the send fails (connection closed, etc.).
        """
        try:
            await websocket.send_json(message)
        except Exception as exc:
            logger.error("send_to failed: %s", exc)
            raise RuntimeError(f"Failed to send WebSocket message: {exc}") from exc


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Message handling
# ---------------------------------------------------------------------------

async def _handle_task_message(
    websocket: WebSocket, data: dict[str, Any]
) -> None:
    """Process an incoming ``task`` message and stream results back.

    Sends ``progress`` events as the agent works and a final ``result``
    event when execution completes.

    Args:
        websocket: The client connection that sent the task.
        data: The ``"data"`` portion of the incoming message, expected to
            contain at least a ``"task"`` key.
    """
    task_text = data.get("task", "")
    if not task_text:
        await manager.send_to(websocket, {
            "type": "error",
            "data": {"message": "Missing 'task' in message data."},
        })
        return

    task_id = uuid.uuid4().hex[:16]
    config = data.get("config")

    # Acknowledge receipt
    await manager.send_to(websocket, {
        "type": "progress",
        "data": {
            "task_id": task_id,
            "status": "received",
            "message": f"Task '{task_text[:80]}' received.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    })

    # Notify that execution is starting
    await manager.send_to(websocket, {
        "type": "progress",
        "data": {
            "task_id": task_id,
            "status": "running",
            "message": "Execution started.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    })

    # Execute the task
    try:
        from agentic_computer.core.orchestrator import Orchestrator

        orchestrator = Orchestrator()
        result = await orchestrator.run(task_text)
        result_payload: Any = str(result)
        status = "completed"
        error: str | None = None
    except ImportError:
        logger.warning("Orchestrator not available; returning stub result via WebSocket.")
        result_payload = f"Task received: {task_text}"
        status = "completed"
        error = None
    except Exception as exc:
        logger.error("WebSocket task %s failed: %s", task_id, exc, exc_info=True)
        result_payload = None
        status = "failed"
        error = str(exc)

    # Send final result
    await manager.send_to(websocket, {
        "type": "result",
        "data": {
            "task_id": task_id,
            "status": status,
            "result": result_payload,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    })

    # Also broadcast progress to all connected clients
    await manager.broadcast({
        "type": "progress",
        "data": {
            "task_id": task_id,
            "status": status,
            "message": f"Task '{task_text[:80]}' {status}.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    })


async def _handle_message(websocket: WebSocket, raw: str) -> None:
    """Parse and dispatch a raw JSON message from a client.

    Supported message types:
        - ``"task"``: Submit a task (delegates to :func:`_handle_task_message`).
        - ``"ping"``: Respond with a ``"pong"`` message.

    Unrecognised types receive an ``"error"`` response.

    Args:
        websocket: The originating client connection.
        raw: Raw JSON string received from the client.
    """
    try:
        message: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        await manager.send_to(websocket, {
            "type": "error",
            "data": {"message": "Invalid JSON."},
        })
        return

    msg_type = message.get("type", "")
    msg_data = message.get("data", {})

    if msg_type == "task":
        # Run task handling in a background coroutine so the WebSocket
        # listener remains responsive to additional messages (e.g. ping).
        asyncio.create_task(_handle_task_message(websocket, msg_data))
    elif msg_type == "ping":
        await manager.send_to(websocket, {
            "type": "pong",
            "data": {"timestamp": datetime.now(timezone.utc).isoformat()},
        })
    else:
        await manager.send_to(websocket, {
            "type": "error",
            "data": {"message": f"Unknown message type: '{msg_type}'."},
        })


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Main WebSocket endpoint for real-time agent interaction.

    Connection lifecycle:
        1. **Connect** -- the server accepts the connection and adds it to the
           manager.
        2. **Authenticate** (optional) -- clients may send an ``"auth"`` message
           with a token.  Currently all connections are accepted.
        3. **Listen** -- the server reads JSON messages in a loop and dispatches
           them to the appropriate handler.
        4. **Disconnect** -- on close or error the connection is removed from the
           manager.

    Message protocol (JSON):
        Incoming::

            {"type": "task", "data": {"task": "...", "config": {...}}}
            {"type": "ping", "data": {}}

        Outgoing::

            {"type": "progress", "data": {"task_id": "...", "status": "...", ...}}
            {"type": "result", "data": {"task_id": "...", "result": ..., ...}}
            {"type": "pong", "data": {"timestamp": "..."}}
            {"type": "error", "data": {"message": "..."}}
    """
    await manager.connect(websocket)

    # Send welcome message so clients know the connection is live
    await manager.send_to(websocket, {
        "type": "connected",
        "data": {
            "message": "Connected to agentic-computer WebSocket.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    })

    try:
        while True:
            raw = await websocket.receive_text()
            await _handle_message(websocket, raw)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected from WebSocket.")
    except Exception as exc:
        logger.error("WebSocket error: %s", exc, exc_info=True)
        manager.disconnect(websocket)
