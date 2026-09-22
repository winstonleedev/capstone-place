from pathlib import Path

import pytest
from place.board import PixelBoard, parse_hex_color, rgb_to_hex


def test_parse_hex_color_valid() -> None:
    assert parse_hex_color("#FFFFFF") == (255, 255, 255)
    assert parse_hex_color("#000000") == (0, 0, 0)
    assert parse_hex_color("#ff5733") == (255, 87, 51)
    assert parse_hex_color("E63946") == (230, 57, 70)
    # 3-char hex
    assert parse_hex_color("#FFF") == (255, 255, 255)
    assert parse_hex_color("#000") == (0, 0, 0)
    assert parse_hex_color("#F00") == (255, 0, 0)


def test_parse_hex_color_invalid() -> None:
    with pytest.raises(ValueError):
        parse_hex_color("invalid")
    with pytest.raises(ValueError):
        parse_hex_color("#12345")
    with pytest.raises(ValueError):
        parse_hex_color("#1234567")


def test_rgb_to_hex() -> None:
    assert rgb_to_hex(255, 255, 255) == "#FFFFFF"
    assert rgb_to_hex(0, 0, 0) == "#000000"
    assert rgb_to_hex(230, 57, 70) == "#E63946"


@pytest.mark.asyncio
async def test_pixel_board_initialization() -> None:
    board = PixelBoard(width=16, height=16, default_color="#FFFFFF")
    assert board.width == 16
    assert board.height == 16
    assert board.total_pixels_placed == 0
    assert board.get_pixel(0, 0) == (255, 255, 255)
    assert board.get_pixel_hex(15, 15) == "#FFFFFF"


@pytest.mark.asyncio
async def test_pixel_board_set_and_get() -> None:
    board = PixelBoard(width=32, height=32, default_color="#000000")
    color = await board.set_pixel(5, 10, 255, 128, 0)
    assert color == "#FF8000"
    assert board.get_pixel(5, 10) == (255, 128, 0)
    assert board.get_pixel_hex(5, 10) == "#FF8000"
    assert board.total_pixels_placed == 1

    # Overwrite
    await board.set_pixel_hex(5, 10, "#00FF00")
    assert board.get_pixel_hex(5, 10) == "#00FF00"
    assert board.total_pixels_placed == 2


@pytest.mark.asyncio
async def test_pixel_board_bounds() -> None:
    board = PixelBoard(width=10, height=10)
    with pytest.raises(ValueError, match="out of bounds"):
        board.get_pixel(10, 0)
    with pytest.raises(ValueError, match="out of bounds"):
        board.get_pixel(-1, 5)
    with pytest.raises(ValueError, match="out of bounds"):
        await board.set_pixel(10, 10, 0, 0, 0)


def test_pixel_board_snapshot_and_png() -> None:
    board = PixelBoard(width=4, height=4, default_color="#FFFFFF")
    snapshot = board.get_snapshot()
    assert snapshot["width"] == 4
    assert snapshot["height"] == 4
    assert len(snapshot["pixels"]) == 16
    assert all(p == "#FFFFFF" for p in snapshot["pixels"])

    png_bytes = board.export_png(scale=2)
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_pixel_board_persists_and_restores() -> None:
    path = Path("test_board_persist.bin")
    board = PixelBoard(width=2, height=2, default_color="#000000", save_path=path)
    await board.set_pixel(0, 0, 255, 0, 0)
    await board.set_pixel(1, 1, 0, 255, 0)

    restored = PixelBoard(width=2, height=2, default_color="#000000", save_path=path)
    assert restored.get_pixel_hex(0, 0) == "#FF0000"
    assert restored.get_pixel_hex(1, 1) == "#00FF00"

    if path.exists():
        path.unlink()

