import asyncio
import io
import re
import struct
from pathlib import Path
from typing import Any
from PIL import Image


HEX_COLOR_REGEX = re.compile(r"^#?([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
BOARD_MAGIC = b"PLACEBIN"


def parse_hex_color(color_str: str) -> tuple[int, int, int]:
    """Parse hex string like #RRGGBB, #RGB, RRGGBB into (R, G, B) integers (0-255)."""
    match = HEX_COLOR_REGEX.match(color_str.strip())
    if not match:
        raise ValueError(f"Invalid hex color string: {color_str}")

    hex_val = match.group(1)
    if len(hex_val) == 3:
        r = int(hex_val[0] * 2, 16)
        g = int(hex_val[1] * 2, 16)
        b = int(hex_val[2] * 2, 16)
    else:
        r = int(hex_val[0:2], 16)
        g = int(hex_val[2:4], 16)
        b = int(hex_val[4:6], 16)
    return r, g, b


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Format RGB tuple as uppercase #RRGGBB."""
    return f"#{r:02X}{g:02X}{b:02X}"


class PixelBoard:
    """Thread-safe in-memory 2D pixel grid for r/place style canvas."""

    def __init__(
        self,
        width: int = 64,
        height: int = 64,
        default_color: str = "#FFFFFF",
        save_path: str | Path | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.save_path = Path(save_path) if save_path is not None else None
        def_r, def_g, def_b = parse_hex_color(default_color)
        self.default_rgb = (def_r, def_g, def_b)
        self.default_hex = rgb_to_hex(def_r, def_g, def_b)

        # Flat bytearray of size width * height * 3 (RGB format)
        total_bytes = width * height * 3
        self._data = bytearray(total_bytes)
        for i in range(0, total_bytes, 3):
            self._data[i] = def_r
            self._data[i + 1] = def_g
            self._data[i + 2] = def_b

        self._lock = asyncio.Lock()
        self.total_pixels_placed = 0
        self._restore_from_disk()

    def _restore_from_disk(self) -> None:
        if self.save_path is None:
            return

        self.save_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.save_path.exists():
            self.save_to_disk()
            return

        payload = self.save_path.read_bytes()
        if len(payload) < 24 or payload[:8] != BOARD_MAGIC:
            self.save_to_disk()
            return

        magic, width, height, total_pixels_placed = struct.unpack(">8sIIQ", payload[:24])
        if width != self.width or height != self.height:
            self.save_to_disk()
            return

        pixel_bytes = payload[24:]
        if len(pixel_bytes) != self.width * self.height * 3:
            self.save_to_disk()
            return

        self._data = bytearray(pixel_bytes)
        self.total_pixels_placed = int(total_pixels_placed)

    def save_to_disk(self) -> None:
        if self.save_path is None:
            return

        self.save_path.parent.mkdir(parents=True, exist_ok=True)
        header = struct.pack(">8sIIQ", BOARD_MAGIC, self.width, self.height, self.total_pixels_placed)
        self.save_path.write_bytes(header + bytes(self._data))

    def _coord_to_index(self, x: int, y: int) -> int:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError(f"Coordinates ({x}, {y}) out of bounds for {self.width}x{self.height} board")
        return (y * self.width + x) * 3

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        idx = self._coord_to_index(x, y)
        return self._data[idx], self._data[idx + 1], self._data[idx + 2]

    def get_pixel_hex(self, x: int, y: int) -> str:
        r, g, b = self.get_pixel(x, y)
        return rgb_to_hex(r, g, b)

    async def set_pixel(self, x: int, y: int, r: int, g: int, b: int) -> str:
        if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
            raise ValueError(f"RGB values must be between 0 and 255, got ({r}, {g}, {b})")

        idx = self._coord_to_index(x, y)
        async with self._lock:
            current_rgb = self._data[idx:idx + 3]
            if tuple(current_rgb) != (r, g, b):
                self._data[idx] = r
                self._data[idx + 1] = g
                self._data[idx + 2] = b
                self.total_pixels_placed += 1
            if self.save_path is not None:
                self.save_to_disk()
            return rgb_to_hex(r, g, b)

    async def set_pixel_hex(self, x: int, y: int, hex_color: str) -> str:
        r, g, b = parse_hex_color(hex_color)
        return await self.set_pixel(x, y, r, g, b)

    def get_raw_bytes(self) -> bytes:
        return bytes(self._data)

    def get_hex_grid(self) -> list[str]:
        """Return a flat list of hex colors row by row."""
        result = []
        data = self._data
        total = self.width * self.height * 3
        for i in range(0, total, 3):
            result.append(f"#{data[i]:02X}{data[i+1]:02X}{data[i+2]:02X}")
        return result

    def get_snapshot(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "total_pixels_placed": self.total_pixels_placed,
            "pixels": self.get_hex_grid(),
        }

    def export_png(self, scale: int = 8) -> bytes:
        """Export board as sharp scaled PNG image."""
        img = Image.frombytes("RGB", (self.width, self.height), bytes(self._data))
        if scale > 1:
            img = img.resize((self.width * scale, self.height * scale), resample=Image.Resampling.NEAREST)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

