(() => {
  // State variables
  let gridWidth = 96;
  let gridHeight = 64;
  let maxTokens = 10;
  let windowSeconds = 60.0;
  let remainingTokens = 10;
  let retryAfterSeconds = 0.0;
  let resetInSeconds = 0.0;
  let lastQuotaCheckTime = Date.now();

  let currentColor = "#E63946";
  let showGrid = false;
  let isEyedropperActive = false;
  let hoverCoord = null;
  let totalPixelsPlaced = 0;
  let socket = null;
  let zoomLevel = 1.0;
  let activeTool = "line";
  let logoClickCount = 0;
  const MIN_ZOOM = 1.0;
  const MAX_ZOOM = 10.0;

  // DOM elements
  const boardCanvas = document.getElementById("boardCanvas");
  const overlayCanvas = document.getElementById("overlayCanvas");
  const canvasWrapper = document.getElementById("canvasWrapper");
  const viewport = document.getElementById("viewport");

  const boardCtx = boardCanvas.getContext("2d", { willReadFrequently: true });
  const overlayCtx = overlayCanvas.getContext("2d");

  const coordDisplay = document.getElementById("coordDisplay");
  const viewerCountEl = document.getElementById("viewerCount");
  const totalPlacedEl = document.getElementById("totalPlaced");
  const gridSizeBadge = document.getElementById("gridSizeBadge");

  const quotaBadge = document.getElementById("quotaBadge");
  const quotaBarFill = document.getElementById("quotaBarFill");
  const cooldownTimerEl = document.getElementById("cooldownTimer");

  const nativeColorPicker = document.getElementById("nativeColorPicker");
  const hexInput = document.getElementById("hexInput");
  const colorPreview = document.getElementById("colorPreview");
  const paletteContainer = document.getElementById("paletteContainer");

  const toggleGridBtn = document.getElementById("toggleGridBtn");
  const zoomInBtn = document.getElementById("zoomInBtn");
  const zoomOutBtn = document.getElementById("zoomOutBtn");
  const downloadBtn = document.getElementById("downloadBtn");
  const eyedropperBtn = document.getElementById("eyedropperBtn");
  const toolboxEl = document.getElementById("toolbox");
  const logoPixelEl = document.querySelector(".logo-pixel");
  const imageImportInput = document.getElementById("imageImportInput");
  const toolButtons = Array.from(document.querySelectorAll(".tool-btn"));
  const toastContainer = document.getElementById("toastContainer");

  // Standard vibrant palette (inspired by iconic pixel art / r/place palettes)
  const PALETTE = [
    "#000000", "#3c3c3c", "#787878", "#b4b4b4", "#ffffff",
    "#6d001a", "#be0039", "#ff4500", "#ffa800", "#ffd635",
    "#00a368", "#00cc78", "#7eed56", "#00756f", "#009eaa",
    "#2450a4", "#3690ea", "#51e9f4", "#493ac1", "#6a5cff",
    "#811e9f", "#b44ac0", "#ff3881", "#ff99aa", "#6d482f",
    "#9c6926", "#ffb470"
  ];

  // Toast Notification
  function showToast(message, type = "info", duration = 3500) {
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(10px)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  // Color selection
  function setColor(hex) {
    if (!hex.startsWith("#")) hex = "#" + hex;
    if (!/^#[0-9A-Fa-f]{6}$/.test(hex)) return;
    currentColor = hex.toUpperCase();
    nativeColorPicker.value = currentColor;
    hexInput.value = currentColor;
    colorPreview.style.backgroundColor = currentColor;

    document.querySelectorAll(".palette-item").forEach(item => {
      item.classList.toggle("selected", item.dataset.color.toUpperCase() === currentColor);
    });
  }

  // Populate Palette
  function initPalette() {
    paletteContainer.innerHTML = "";
    PALETTE.forEach(color => {
      const swatch = document.createElement("div");
      swatch.className = "palette-item";
      swatch.dataset.color = color;
      swatch.style.backgroundColor = color;
      swatch.title = color;
      if (color.toUpperCase() === currentColor.toUpperCase()) {
        swatch.classList.add("selected");
      }
      swatch.addEventListener("click", () => {
        if (isEyedropperActive) toggleEyedropper(false);
        setColor(color);
      });
      paletteContainer.appendChild(swatch);
    });
  }

  // Eyedropper toggle
  function toggleEyedropper(active) {
    isEyedropperActive = active !== undefined ? active : !isEyedropperActive;
    eyedropperBtn.classList.toggle("active", isEyedropperActive);
    canvasWrapper.classList.toggle("eyedropper-mode", isEyedropperActive);
  }

  function setActiveTool(tool) {
    activeTool = tool;
    toolButtons.forEach((button) => {
      const isSelected = button.dataset.tool === tool;
      button.classList.toggle("active", isSelected);
    });
  }

  function unlockToolbox() {
    if (!toolboxEl) return;
    if (toolboxEl.classList.contains("is-visible")) return;

    toolboxEl.classList.add("is-visible");
    toolboxEl.setAttribute("aria-hidden", "false");
    showToast("Advanced toolbox unlocked", "success", 1800);
  }

  // Canvas Viewport & Scaling
  function setZoomLevel(nextZoom) {
    zoomLevel = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, nextZoom));
    canvasWrapper.style.transform = `scale(${zoomLevel})`;
    renderOverlay();
  }

  function resizeCanvasDisplay() {
    const availWidth = Math.max(100, viewport.clientWidth - 24);
    const availHeight = Math.max(100, viewport.clientHeight - 24);
    const aspectRatio = gridWidth / gridHeight;

    let displayWidth = availWidth;
    let displayHeight = displayWidth / aspectRatio;

    if (displayHeight > availHeight) {
      displayHeight = availHeight;
      displayWidth = displayHeight * aspectRatio;
    }

    displayWidth = Math.floor(displayWidth);
    displayHeight = Math.floor(displayHeight);

    canvasWrapper.style.width = `${displayWidth}px`;
    canvasWrapper.style.height = `${displayHeight}px`;

    // Ensure overlay canvas internal size matches display size for crisp grid drawing
    overlayCanvas.width = displayWidth;
    overlayCanvas.height = displayHeight;

    setZoomLevel(zoomLevel);
    renderOverlay();
  }

  // Draw overlay (gridlines and hover cursor)
  function renderOverlay() {
    const w = overlayCanvas.width;
    const h = overlayCanvas.height;
    if (!w || !h) return;
    overlayCtx.clearRect(0, 0, w, h);

    const cellW = w / gridWidth;
    const cellH = h / gridHeight;

    // Grid lines
    if (showGrid && cellW >= 2) {
      overlayCtx.strokeStyle = "rgba(0, 0, 0, 0.25)";
      overlayCtx.lineWidth = 1;
      overlayCtx.beginPath();
      for (let x = 0; x <= gridWidth; x++) {
        const px = Math.round(x * cellW) + 0.5;
        overlayCtx.moveTo(px, 0);
        overlayCtx.lineTo(px, h);
      }
      for (let y = 0; y <= gridHeight; y++) {
        const py = Math.round(y * cellH) + 0.5;
        overlayCtx.moveTo(0, py);
        overlayCtx.lineTo(w, py);
      }
      overlayCtx.stroke();
    }

    // Hover highlight: show only the current pixel as a single-pixel outline
    if (hoverCoord) {
      const { x, y } = hoverCoord;
      const px = Math.round(x * cellW) + 0.5;
      const py = Math.round(y * cellH) + 0.5;
      const pw = Math.max(1, Math.round(cellW));
      const ph = Math.max(1, Math.round(cellH));

      if (isEyedropperActive) {
        overlayCtx.fillStyle = "#3b82f6";
        overlayCtx.beginPath();
        overlayCtx.arc(px, py, 1.5, 0, Math.PI * 2);
        overlayCtx.fill();
      } else {
        // overlayCtx.strokeStyle = "#ffffff";
        // overlayCtx.lineWidth = 1.5;
        // overlayCtx.strokeRect(px - 0.5, py - 0.5, pw - 1, ph - 1);

        overlayCtx.fillStyle = "#000000";
        overlayCtx.beginPath();
        overlayCtx.arc(px, py, 1.25, 0, Math.PI * 2);
        overlayCtx.fill();
      }
    }
  }

  // Paint a single pixel on the main board canvas
  function paintPixel(x, y, hexColor) {
    if (!hexColor.startsWith("#")) hexColor = "#" + hexColor;
    boardCtx.fillStyle = hexColor;
    boardCtx.fillRect(x, y, 1, 1);
  }

  // Fetch initial board state
  async function loadBoard() {
    try {
      const res = await fetch("/api/board");
      if (!res.ok) throw new Error("Failed to load board snapshot");
      const data = await res.json();
      gridWidth = data.width;
      gridHeight = data.height;
      totalPixelsPlaced = data.total_pixels_placed || 0;
      totalPlacedEl.textContent = totalPixelsPlaced.toLocaleString();
      gridSizeBadge.textContent = `${gridWidth}×${gridHeight}`;

      boardCanvas.width = gridWidth;
      boardCanvas.height = gridHeight;

      // Disable image smoothing for ultra sharp pixel rendering
      boardCtx.imageSmoothingEnabled = false;

      // Draw all pixels
      const pixels = data.pixels;
      for (let y = 0; y < gridHeight; y++) {
        for (let x = 0; x < gridWidth; x++) {
          const idx = y * gridWidth + x;
          boardCtx.fillStyle = pixels[idx];
          boardCtx.fillRect(x, y, 1, 1);
        }
      }

      resizeCanvasDisplay();
    } catch (err) {
      console.error(err);
      showToast("Error loading canvas: " + err.message, "error");
    }
  }

  // Quota & Rate Limit Updates
  function updateQuotaUI() {
    quotaBadge.textContent = `${remainingTokens} / ${maxTokens} pixels`;
    if (remainingTokens === 0) {
      quotaBadge.classList.add("exhausted");
      quotaBarFill.classList.add("cooldown");
      quotaBarFill.style.width = "0%";
      const wait = Math.max(1, Math.ceil(retryAfterSeconds || resetInSeconds));
      cooldownTimerEl.textContent = `Cooldown: wait ${wait}s`;
    } else {
      quotaBadge.classList.remove("exhausted");
      quotaBarFill.classList.remove("cooldown");
      const pct = (remainingTokens / maxTokens) * 100;
      quotaBarFill.style.width = `${pct}%`;
      if (remainingTokens === maxTokens) {
        cooldownTimerEl.textContent = "Ready to place";
      } else {
        const nextIn = Math.max(1, Math.ceil(resetInSeconds));
        cooldownTimerEl.textContent = `Next pixel in ~${nextIn}s`;
      }
    }
  }

  async function checkCooldown() {
    try {
      const res = await fetch("/api/cooldown");
      if (!res.ok) return;
      const data = await res.json();
      remainingTokens = data.remaining;
      retryAfterSeconds = data.retry_after;
      resetInSeconds = data.reset_in;
      maxTokens = data.max_pixels;
      windowSeconds = data.window_seconds;
      lastQuotaCheckTime = Date.now();
      updateQuotaUI();
    } catch (e) {
      console.debug("Cooldown check error:", e);
    }
  }

  // Client-side local cooldown countdown tick
  setInterval(() => {
    const now = Date.now();
    const elapsedSec = (now - lastQuotaCheckTime) / 1000.0;
    lastQuotaCheckTime = now;

    let checkNeeded = false;

    if (retryAfterSeconds > 0) {
      retryAfterSeconds = Math.max(0, retryAfterSeconds - elapsedSec);
      if (retryAfterSeconds === 0) {
        checkNeeded = true;
      }
    }

    if (resetInSeconds > 0) {
      resetInSeconds = Math.max(0, resetInSeconds - elapsedSec);
      if (resetInSeconds === 0) {
        checkNeeded = true;
      }
    }

    if (checkNeeded) {
      checkCooldown();
    } else {
      updateQuotaUI();
    }
  }, 250);

  // Periodic resync with server every 5 seconds
  setInterval(checkCooldown, 5000);
  window.addEventListener("focus", checkCooldown);

  // Mouse / Touch coordinate resolver
  function getGridCoordinates(event) {
    const rect = canvasWrapper.getBoundingClientRect();
    let clientX, clientY;
    if (event.touches && event.touches.length > 0) {
      clientX = event.touches[0].clientX;
      clientY = event.touches[0].clientY;
    } else if (event.changedTouches && event.changedTouches.length > 0) {
      clientX = event.changedTouches[0].clientX;
      clientY = event.changedTouches[0].clientY;
    } else {
      clientX = event.clientX;
      clientY = event.clientY;
    }

    if (
      clientX < rect.left ||
      clientX > rect.right ||
      clientY < rect.top ||
      clientY > rect.bottom
    ) {
      return null;
    }

    const localX = clientX - rect.left;
    const localY = clientY - rect.top;
    const unscaledX = localX / Math.max(1e-6, rect.width) * boardCanvas.width;
    const unscaledY = localY / Math.max(1e-6, rect.height) * boardCanvas.height;

    const gx = Math.floor(unscaledX);
    const gy = Math.floor(unscaledY);

    if (gx < 0 || gx >= gridWidth || gy < 0 || gy >= gridHeight) {
      return null;
    }
    return { x: gx, y: gy };
  }

  // Place pixel action
  async function handleCanvasClick(event) {
    const coord = getGridCoordinates(event);
    if (!coord) return;

    if (isEyedropperActive) {
      // Sample color from board canvas
      const pixelData = boardCtx.getImageData(coord.x, coord.y, 1, 1).data;
      const r = pixelData[0].toString(16).padStart(2, "0");
      const g = pixelData[1].toString(16).padStart(2, "0");
      const b = pixelData[2].toString(16).padStart(2, "0");
      const picked = `#${r}${g}${b}`.toUpperCase();
      setColor(picked);
      toggleEyedropper(false);
      showToast(`Color picked: ${picked}`, "info", 1800);
      return;
    }

    // Check local quota
    // Check local quota; if 0, verify with server before rejecting
    if (remainingTokens <= 0) {
      const wait = Math.max(1, Math.ceil(retryAfterSeconds));
      showToast(`Rate limited! You can place 10 pixels/min. Wait ${wait}s.`, "warning");
      return;
      await checkCooldown();
      if (remainingTokens <= 0) {
        const wait = Math.max(1, Math.ceil(retryAfterSeconds || resetInSeconds || 1));
        showToast(`Rate limited! 10 pixels/min max. Wait ${wait}s.`, "warning");
        return;
      }
    }

    const { x, y } = coord;
    const colorToPlace = currentColor;

    // Optimistic local update
    paintPixel(x, y, colorToPlace);
    renderOverlay();

    try {
      const res = await fetch("/api/pixel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ x, y, color: colorToPlace }),
      });

      if (res.status === 429) {
        const err = await res.json();
        retryAfterSeconds = err.retry_after || 6.0;
        resetInSeconds = err.reset_in || retryAfterSeconds;
        remainingTokens = 0;
        updateQuotaUI();
        const wait = Math.max(1, Math.ceil(retryAfterSeconds));
        showToast(`Rate limit reached: wait ${wait}s before next pixel.`, "error");
        await loadBoard();
        return;
      }

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to place pixel");
      }

      const data = await res.json();
      remainingTokens = data.remaining;
      resetInSeconds = data.reset_in;
      retryAfterSeconds = 0;
      retryAfterSeconds = data.retry_after || (remainingTokens === 0 ? resetInSeconds : 0.0);
      updateQuotaUI();
    } catch (err) {
      console.error(err);
      showToast(err.message, "error");
      await loadBoard();
    }
  }

  // WebSocket Live Sync
  function connectWebSocket() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${location.host}/ws`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      console.log("WebSocket connected");
    };

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "pixel") {
          paintPixel(msg.x, msg.y, msg.color);
          totalPixelsPlaced = msg.total_pixels_placed;
          totalPlacedEl.textContent = totalPixelsPlaced.toLocaleString();
        } else if (msg.type === "viewers") {
          viewerCountEl.textContent = msg.count;
        } else if (msg.type === "init") {
          viewerCountEl.textContent = msg.viewers;
          totalPixelsPlaced = msg.total_pixels_placed;
          totalPlacedEl.textContent = totalPixelsPlaced.toLocaleString();
        }
      } catch (err) {
        console.error("WS parse error:", err);
      }
    };

    socket.onclose = () => {
      console.log("WebSocket disconnected, reconnecting in 2s...");
      setTimeout(connectWebSocket, 2000);
    };

    socket.onerror = () => {
      socket.close();
    };
  }

  // Event Listeners
  if (logoPixelEl) {
    logoPixelEl.addEventListener("click", () => {
      logoClickCount += 1;

      if (logoClickCount >= 5) {
        unlockToolbox();
        logoClickCount = 5;
        return;
      }

      if (logoClickCount < 5) {
        const remaining = 5 - logoClickCount;
        showToast(`Toolbox unlock: ${remaining} click${remaining === 1 ? "" : "s"} left`, "info", 900);
      }
    });
  }

  toolButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const tool = button.dataset.tool;
      if (!tool) return;
      setActiveTool(tool);
    });
  });

  if (imageImportInput) {
    imageImportInput.addEventListener("change", (event) => {
      const file = event.target.files && event.target.files[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = (loadEvent) => {
        const image = new Image();
        image.onload = () => {
          const tempCanvas = document.createElement("canvas");
          tempCanvas.width = image.width;
          tempCanvas.height = image.height;
          const tempCtx = tempCanvas.getContext("2d");
          tempCtx.drawImage(image, 0, 0);

          const { data, width, height } = tempCtx.getImageData(0, 0, image.width, image.height);
          const boardImageData = boardCtx.createImageData(width, height);
          boardImageData.data.set(data);
          boardCtx.putImageData(boardImageData, 0, 0);
          showToast(`Imported image: ${file.name}`, "success", 1800);
          renderOverlay();
        };
        image.src = loadEvent.target.result;
      };
      reader.readAsDataURL(file);
    });
  }

  window.addEventListener("resize", resizeCanvasDisplay);

  viewport.addEventListener("wheel", (event) => {
    event.preventDefault();
    const delta = event.deltaY > 0 ? -0.1 : 0.1;
    setZoomLevel(zoomLevel + delta);
  }, { passive: false });

  zoomInBtn.addEventListener("click", () => setZoomLevel(zoomLevel + 0.1));
  zoomOutBtn.addEventListener("click", () => setZoomLevel(zoomLevel - 0.1));

  canvasWrapper.addEventListener("mousemove", (e) => {
    const coord = getGridCoordinates(e);
    hoverCoord = coord;
    if (coord) {
      coordDisplay.textContent = `X: ${coord.x}, Y: ${coord.y}`;
    } else {
      coordDisplay.textContent = "X: --, Y: --";
    }
    renderOverlay();
  });

  canvasWrapper.addEventListener("mouseleave", () => {
    hoverCoord = null;
    coordDisplay.textContent = "X: --, Y: --";
    renderOverlay();
  });

  canvasWrapper.addEventListener("click", handleCanvasClick);

  toggleGridBtn.addEventListener("click", () => {
    showGrid = !showGrid;
    toggleGridBtn.classList.toggle("active", showGrid);
    renderOverlay();
  });

  downloadBtn.addEventListener("click", () => {
    const a = document.createElement("a");
    a.href = "/api/board/image?scale=8";
    a.download = `place-${Date.now()}.png`;
    a.click();
    showToast("Downloading board snapshot...", "success", 2000);
  });

  eyedropperBtn.addEventListener("click", () => {
    toggleEyedropper();
  });

  nativeColorPicker.addEventListener("input", (e) => {
    setColor(e.target.value);
  });

  hexInput.addEventListener("change", (e) => {
    setColor(e.target.value);
  });

  hexInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      setColor(e.target.value);
      hexInput.blur();
    }
  });

  // Initialization
  async function init() {
    showGrid = false;
    toggleGridBtn.classList.remove("active");
    setColor("#E63946");
    initPalette();

    // Pre-initialize canvas dimensions and white background immediately
    boardCanvas.width = gridWidth;
    boardCanvas.height = gridHeight;
    boardCtx.imageSmoothingEnabled = false;
    boardCtx.fillStyle = "#FFFFFF";
    boardCtx.fillRect(0, 0, gridWidth, gridHeight);
    setZoomLevel(1.0);
    resizeCanvasDisplay();

    await loadBoard();
    await checkCooldown();
    connectWebSocket();
  }

  init();
})();

