import argparse

import uvicorn

from place.app import create_app
from place.board import import_board
from place.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the place collaborative pixel board server.")
    parser.add_argument("--host", default=settings.host, help=f"Host to bind (default: {settings.host})")
    parser.add_argument("--port", type=int, default=settings.port, help=f"Port to bind (default: {settings.port})")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument(
        "--import-board",
        default=None,
        help="Path to an existing board snapshot to load and center on the current board size",
    )
    args = parser.parse_args()

    imported_board = None
    if args.import_board:
        imported_board = import_board(
            width=settings.grid_width,
            height=settings.grid_height,
            board_path=args.import_board,
            default_color=settings.default_color,
        )
        print(f"📥 Imported board from {args.import_board} into {settings.grid_width}x{settings.grid_height} canvas")

    app = create_app(
        grid_width=settings.grid_width,
        grid_height=settings.grid_height,
        rate_limit_pixels=settings.rate_limit_pixels,
        rate_limit_window=settings.rate_limit_window_seconds,
        board_path=settings.board_path,
        initial_board=imported_board,
    )

    print(f"🎨 Starting `place` server on http://{args.host}:{args.port}")
    print(f"📐 Grid Size: {settings.grid_width}x{settings.grid_height} pixels")
    print(f"⏱️  Rate Limit: {settings.rate_limit_pixels} pixels / {settings.rate_limit_window_seconds}s per client IP")

    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()

