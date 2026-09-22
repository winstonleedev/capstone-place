import asyncio
import json
import logging
from typing import Any
from starlette.websockets import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and real-time event broadcasting."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    @property
    def viewer_count(self) -> int:
        return len(self.active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        await self.broadcast_viewer_count()

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        await self.broadcast_viewer_count()

    async def broadcast(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message)
        dead_connections: list[WebSocket] = []

        async with self._lock:
            current_connections = list(self.active_connections)

        for connection in current_connections:
            try:
                await connection.send_text(payload)
            except Exception as e:
                logger.debug(f"Failed to send to websocket: {e}")
                dead_connections.append(connection)

        if dead_connections:
            async with self._lock:
                for dead in dead_connections:
                    if dead in self.active_connections:
                        self.active_connections.remove(dead)

    async def broadcast_pixel(self, x: int, y: int, color: str, total_placed: int) -> None:
        await self.broadcast({
            "type": "pixel",
            "x": x,
            "y": y,
            "color": color,
            "total_pixels_placed": total_placed,
        })

    async def broadcast_viewer_count(self) -> None:
        await self.broadcast({
            "type": "viewers",
            "count": self.viewer_count,
        })

