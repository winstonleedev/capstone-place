# 🎨 `place`

A single-screen collaborative pixel canvas inspired by Reddit's r/place. Built with Python, FastAPI, WebSockets, HTML5 Canvas, and managed using `uv`.

## Features

- 🖥️ **Single-Screen Fit**: A 96×64 pixel grid configured with crisp pixel rendering (`image-rendering: pixelated`) sized to maximize viewport space without page scrolling.
- 🎨 **Full RGB Color Selection**: Pick any 24-bit RGB color with a native color picker, hex code input (`#RRGGBB`), or a 27-color quick-select palette. Includes an **Eyedropper** tool to sample colors directly from the canvas.
- ⏱️ **Per-IP Rate Limiting**: Enforces a strict limit of **10 pixel placements per minute** per client IP using an atomic sliding-window algorithm. Returns HTTP 429 with `Retry-After` headers and live UI cooldown feedback.
- ⚡ **Real-Time Synchronization**: Multi-client live updates over WebSockets so all connected users see pixel changes instantly without refreshing.
- 📸 **PNG Export**: One-click download of the current board snapshot as a sharp scaled PNG.
- 🛠️ **Powered by `uv`**: Fast dependency management, script running, and packaging.

---

## Quick Start with `uv`

### 1. Install Dependencies
```bash
uv sync
```

### 2. Start the Server
```bash
# Using the installed CLI entrypoint
uv run place-server

# Or run directly via uvicorn
uv run uvicorn place.app:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser and navigate to:
```
http://localhost:8000
```

---

## Configuration

You can configure the server using CLI arguments or environment variables:

| Setting | Env Var | Default | Description |
| :--- | :--- | :--- | :--- |
| **Grid Width** | `PLACE_GRID_WIDTH` | `96` | Number of horizontal pixels |
| **Grid Height** | `PLACE_GRID_HEIGHT` | `64` | Number of vertical pixels |
| **Rate Limit** | `PLACE_RATE_LIMIT_PIXELS` | `10` | Allowed pixels per window |
| **Window** | `PLACE_RATE_LIMIT_WINDOW` | `60.0` | Rate limit window in seconds |
| **Host** | `PLACE_HOST` | `0.0.0.0` | Bind host address |
| **Port** | `PLACE_PORT` | `8000` | Bind port |

Example:
```bash
PLACE_GRID_WIDTH=80 PLACE_GRID_HEIGHT=80 PLACE_RATE_LIMIT_PIXELS=10 uv run place --port 8080
```

---

## HTTP REST & WebSocket API

### `GET /api/config`
Returns board configuration and rate limit parameters.

### `GET /api/board`
Returns current board snapshot with width, height, total pixels placed, and an array of hex colors.

### `GET /api/board/raw`
Returns raw binary RGB byte stream (`width * height * 3` bytes).

### `GET /api/board/image?scale=8`
Exports board as a sharp PNG image scaled by nearest-neighbor interpolation.

### `GET /api/cooldown`
Returns caller's remaining placement quota, reset timer, and client IP.

### `POST /api/pixel`
Places a pixel at `(x, y)` with the specified color.

**Request body:**
```json
{
  "x": 32,
  "y": 32,
  "color": "#E63946"
}
```
*Alternatively, provide `"r"`, `"g"`, `"b"` integers (0-255).*

**Success Response (`200 OK`):**
```json
{
  "success": true,
  "x": 32,
  "y": 32,
  "color": "#E63946",
  "remaining": 9,
  "reset_in": 60.0,
  "total_pixels_placed": 1
}
```

**Rate Limited Response (`429 Too Many Requests`):**
```json
{
  "detail": "Rate limit exceeded. Each client can place 10 pixels per 60s. Try again in 14.2s.",
  "remaining": 0,
  "retry_after": 14.2,
  "reset_in": 14.2
}
```
*Includes `Retry-After: 15` response header.*

### `WS /ws`
Real-time WebSocket connection broadcasting `{ "type": "pixel", "x": x, "y": y, "color": "#...", "total_pixels_placed": N }` and viewer counts.

---

## Running Tests

Run the test suite with:
```bash
uv run pytest
```

