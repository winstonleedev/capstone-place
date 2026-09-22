import pytest
from httpx import ASGITransport, AsyncClient
from place.app import create_app


@pytest.fixture
def app():
    return create_app(
        grid_width=16,
        grid_height=16,
        rate_limit_pixels=10,
        rate_limit_window=60.0,
    )


@pytest.mark.asyncio
async def test_get_config(app) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/config")
        assert res.status_code == 200
        data = res.json()
        assert data["width"] == 16
        assert data["height"] == 16
        assert data["rate_limit_pixels"] == 10
        assert data["rate_limit_window_seconds"] == 60.0


@pytest.mark.asyncio
async def test_get_board(app) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/board")
        assert res.status_code == 200
        data = res.json()
        assert data["width"] == 16
        assert data["height"] == 16
        assert len(data["pixels"]) == 16 * 16


@pytest.mark.asyncio
async def test_get_board_raw_and_image(app) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        raw_res = await client.get("/api/board/raw")
        assert raw_res.status_code == 200
        assert len(raw_res.content) == 16 * 16 * 3

        img_res = await client.get("/api/board/image?scale=4")
        assert img_res.status_code == 200
        assert img_res.headers["content-type"] == "image/png"
        assert img_res.content[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_place_pixel_hex_and_rgb(app) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Place with hex string
        res = await client.post("/api/pixel", json={"x": 5, "y": 5, "color": "#FF0000"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["x"] == 5
        assert data["y"] == 5
        assert data["color"] == "#FF0000"
        assert data["remaining"] == 9

        # Place with r, g, b integers
        res2 = await client.post("/api/pixel", json={"x": 6, "y": 6, "r": 0, "g": 255, "b": 0})
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["success"] is True
        assert data2["color"] == "#00FF00"
        assert data2["remaining"] == 8


@pytest.mark.asyncio
async def test_place_pixel_invalid_inputs(app) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Out of bounds
        res1 = await client.post("/api/pixel", json={"x": 20, "y": 5, "color": "#FF0000"})
        assert res1.status_code == 400

        # Invalid hex
        res2 = await client.post("/api/pixel", json={"x": 0, "y": 0, "color": "not-a-color"})
        assert res2.status_code == 400

        # Missing color
        res3 = await client.post("/api/pixel", json={"x": 0, "y": 0})
        assert res3.status_code == 400


@pytest.mark.asyncio
async def test_rate_limiting_10_per_minute(app) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"X-Forwarded-For": "203.0.113.42"}

        # Place 10 pixels successfully
        for i in range(10):
            res = await client.post(
                "/api/pixel",
                json={"x": i, "y": 0, "color": "#123456"},
                headers=headers,
            )
            assert res.status_code == 200
            assert res.json()["remaining"] == 9 - i

        # 11th pixel should be rejected with 429
        res_blocked = await client.post(
            "/api/pixel",
            json={"x": 10, "y": 0, "color": "#123456"},
            headers=headers,
        )
        assert res_blocked.status_code == 429
        assert "Retry-After" in res_blocked.headers
        data = res_blocked.json()
        assert "Rate limit exceeded" in data["detail"]
        assert data["remaining"] == 0
        assert data["retry_after"] > 0

        # Check cooldown endpoint for this client
        res_cd = await client.get("/api/cooldown", headers=headers)
        assert res_cd.status_code == 200
        cd_data = res_cd.json()
        assert cd_data["allowed"] is False
        assert cd_data["remaining"] == 0
        assert cd_data["retry_after"] > 0
        assert cd_data["ip"] == "203.0.113.42"


@pytest.mark.asyncio
async def test_static_files_served(app) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_root = await client.get("/")
        assert res_root.status_code == 200
        assert "place" in res_root.text

        res_css = await client.get("/static/style.css")
        assert res_css.status_code == 200
        assert "canvas-viewport" in res_css.text

        res_js = await client.get("/static/app.js")
        assert res_js.status_code == 200
        assert "boardCanvas" in res_js.text

