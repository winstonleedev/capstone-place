import math
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from place.board import PixelBoard, parse_hex_color, rgb_to_hex
from place.config import settings
from place.notifier import ConnectionManager
from place.rate_limiter import SlidingWindowRateLimiter, extract_client_ip


class PixelRequest(BaseModel):
    x: int = Field(..., description="0-indexed X coordinate")
    y: int = Field(..., description="0-indexed Y coordinate")
    color: str | None = Field(None, description="Hex color like #FF5733 or #FFF")
    r: int | None = Field(None, ge=0, le=255, description="Red component 0-255")
    g: int | None = Field(None, ge=0, le=255, description="Green component 0-255")
    b: int | None = Field(None, ge=0, le=255, description="Blue component 0-255")


def create_app(
    grid_width: int = settings.grid_width,
    grid_height: int = settings.grid_height,
    rate_limit_pixels: int = settings.rate_limit_pixels,
    rate_limit_window: float = settings.rate_limit_window_seconds,
) -> FastAPI:
    app = FastAPI(
        title="place",
        description="A real-time collaborative pixel canvas with per-IP rate limiting.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    board = PixelBoard(width=grid_width, height=grid_height, default_color=settings.default_color)
    rate_limiter = SlidingWindowRateLimiter(max_requests=rate_limit_pixels, window_seconds=rate_limit_window)
    notifier = ConnectionManager()

    # Store references on app state for tests / programmatic access
    app.state.board = board
    app.state.rate_limiter = rate_limiter
    app.state.notifier = notifier

    @app.api_route("/api/config", methods=["GET", "HEAD"])
    async def get_config() -> dict[str, Any]:
        return {
            "width": board.width,
            "height": board.height,
            "rate_limit_pixels": rate_limiter.max_requests,
            "rate_limit_window_seconds": rate_limiter.window_seconds,
            "default_color": board.default_hex,
        }

    @app.api_route("/api/board", methods=["GET", "HEAD"])
    async def get_board() -> dict[str, Any]:
        return board.get_snapshot()

    @app.api_route("/api/board/raw", methods=["GET", "HEAD"])
    async def get_board_raw() -> Response:
        return Response(content=board.get_raw_bytes(), media_type="application/octet-stream")

    @app.api_route("/api/board/image", methods=["GET", "HEAD"])
    async def get_board_image(scale: int = 8) -> Response:
        clamped_scale = max(1, min(scale, 32))
        png_bytes = board.export_png(scale=clamped_scale)
        return Response(content=png_bytes, media_type="image/png")

    @app.api_route("/api/cooldown", methods=["GET", "HEAD"])
    async def get_cooldown(request: Request) -> dict[str, Any]:
        client_ip = extract_client_ip(request)
        status_info = await rate_limiter.get_status(client_ip)
        return {
            "ip": client_ip,
            "allowed": status_info.allowed,
            "remaining": status_info.remaining,
            "max_pixels": rate_limiter.max_requests,
            "window_seconds": rate_limiter.window_seconds,
            "retry_after": status_info.retry_after,
            "reset_in": status_info.reset_in,
        }

    @app.post("/api/pixel")
    async def place_pixel(payload: PixelRequest, request: Request) -> dict[str, Any]:
        # Validate coordinates
        if not (0 <= payload.x < board.width and 0 <= payload.y < board.height):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Coordinates ({payload.x}, {payload.y}) out of range. Grid is {board.width}x{board.height}.",
            )

        # Validate & resolve color
        if payload.color:
            try:
                r, g, b = parse_hex_color(payload.color)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        elif payload.r is not None and payload.g is not None and payload.b is not None:
            r, g, b = payload.r, payload.g, payload.b
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must provide either 'color' (hex string) or 'r', 'g', 'b' integer values (0-255).",
            )

        client_ip = extract_client_ip(request)
        limit_status = await rate_limiter.check_and_consume(client_ip)

        if not limit_status.allowed:
            retry_seconds = max(1, math.ceil(limit_status.retry_after))
            return Response(
                content=(
                    f'{{"detail":"Rate limit exceeded. Each client can place {rate_limiter.max_requests} pixels '
                    f'per {int(rate_limiter.window_seconds)}s. Try again in {limit_status.retry_after:.1f}s.",'
                    f'"remaining":0,"retry_after":{limit_status.retry_after},"reset_in":{limit_status.reset_in}}}'
                ),
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
                headers={"Retry-After": str(retry_seconds)},
            )

        color_hex = await board.set_pixel(payload.x, payload.y, r, g, b)

        # Broadcast update to connected clients
        await notifier.broadcast_pixel(
            x=payload.x,
            y=payload.y,
            color=color_hex,
            total_placed=board.total_pixels_placed,
        )

        return {
            "success": True,
            "x": payload.x,
            "y": payload.y,
            "color": color_hex,
            "remaining": limit_status.remaining,
            "reset_in": limit_status.reset_in,
            "total_pixels_placed": board.total_pixels_placed,
        }

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await notifier.connect(websocket)
        try:
            # Send initial state info
            await websocket.send_json({
                "type": "init",
                "width": board.width,
                "height": board.height,
                "total_pixels_placed": board.total_pixels_placed,
                "viewers": notifier.viewer_count,
            })
            while True:
                # Keep alive / listen for client ping
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            await notifier.disconnect(websocket)
        except Exception:
            await notifier.disconnect(websocket)

    # Static file serving
    # Check possible static directories
    pkg_static = Path(__file__).parent / "static"
    root_static = Path.cwd() / "static"
    static_dir = pkg_static if pkg_static.exists() else root_static

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.api_route("/", methods=["GET", "HEAD"])
        async def serve_index() -> FileResponse:
            index_path = static_dir / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            raise HTTPException(status_code=404, detail="index.html not found")

    return app


app = create_app()
