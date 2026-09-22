import argparse
import uvicorn
from place.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the place collaborative pixel board server.")
    parser.add_argument("--host", default=settings.host, help=f"Host to bind (default: {settings.host})")
    parser.add_argument("--port", type=int, default=settings.port, help=f"Port to bind (default: {settings.port})")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    print(f"🎨 Starting `place` server on http://{args.host}:{args.port}")
    print(f"📐 Grid Size: {settings.grid_width}x{settings.grid_height} pixels")
    print(f"⏱️  Rate Limit: {settings.rate_limit_pixels} pixels / {settings.rate_limit_window_seconds}s per client IP")

    uvicorn.run("place.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()

