import os
from dataclasses import dataclass


@dataclass
class Settings:
    grid_width: int = int(os.getenv("PLACE_GRID_WIDTH", "64"))
    grid_height: int = int(os.getenv("PLACE_GRID_HEIGHT", "64"))
    rate_limit_pixels: int = int(os.getenv("PLACE_RATE_LIMIT_PIXELS", "10"))
    rate_limit_window_seconds: float = float(os.getenv("PLACE_RATE_LIMIT_WINDOW", "60.0"))
    host: str = os.getenv("PLACE_HOST", "0.0.0.0")
    port: int = int(os.getenv("PLACE_PORT", "8000"))
    default_color: str = os.getenv("PLACE_DEFAULT_COLOR", "#FFFFFF")


settings = Settings()

