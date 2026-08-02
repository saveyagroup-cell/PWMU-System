/**
 * Shared logic for dedicated single-module pages.
 * setupModulePanel(moduleName, initialActive, useRawFeed)
 *   useRawFeed=true  → /raw_feed/ + /api/live_boxes/ canvas overlay (smooth!)
 *   useRawFeed=false → /video_feed/ annotated stream (legacy)
 */

function tickClock() {
  const el = document.getElementById("live-clock");
  if (!el) return;
  const now = new Date();
  el.textContent = now.toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true,
  });
}

/**
 * Deterministic color per label (same label always gets the same color).
 * Avoids the jarring "random color each frame" problem.
 */
function _labelColor(label) {
  const COLORS = [
    "#16A34A", "#2563EB", "#DC2626", "#D97706",
    "#7C3AED", "#0EA5E9", "#DB2777", "#65A30D",
  ];
  let h = 0;
  for (let i = 0; i < label.length; i++) h = (h * 31 + label.charCodeAt(i)) >>> 0;
  return COLORS[h % COLORS.length];
}

/**
 * Draw detection boxes onto a canvas overlay.
 * @param {CanvasRenderingContext2D} ctx
 * @param {Array}  boxes  - [{x1,y1,x2,y2,label,conf}, ...]
 * @param {number} srcW   - inference frame width
 * @param {number} srcH   - inference frame height
 * @param {number} dstW   - canvas display width
 * @param {number} dstH   - canvas display height
 */
function _drawBoxes(ctx, boxes, srcW, srcH, dstW, dstH) {
  ctx.clearRect(0, 0, dstW, dstH);
  if (!boxes || !boxes.length) return;

  const sx = dstW / (srcW || 1);
  const sy = dstH / (srcH || 1);

  boxes.forEach((b) => {
    const x1 = b.x1 * sx, y1 = b.y1 * sy;
    const x2 = b.x2 * sx, y2 = b.y2 * sy;
    const color = _labelColor(b.label || "");
    const confStr = b.conf != null ? ` ${(b.conf * 1).toFixed(2)}` : "";
    const text = `${b.label}${confStr}`;

    // Box
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

    // Label background
    ctx.font = "bold 12px 'Segoe UI', sans-serif";
    const tw = ctx.measureText(text).width;
    const th = 16;
    const labelY = Math.max(0, y1 - th - 2);
    ctx.fillStyle = color;
    ctx.fillRect(x1, labelY, tw + 8, th + 2);

    // Label text
    ctx.fillStyle = "#fff";
    ctx.fillText(text, x1 + 4, labelY + th - 2);
  });
}


function setupModulePanel(moduleName, initialActive, useRawFeed) {
  const feedImg    = document.getElementById("feed-img");
  const overlay    = document.getElementById("overlay-canvas");
  const placeholder = document.getElementById("feed-placeholder");
  const liveBadge  = document.getElementById("live-badge");
  const toggleBtn  = document.getElementById("toggle-btn");
  const uploadInput = document.getElementById("upload-input");

  let octx          = overlay ? overlay.getContext("2d") : null;
  let boxesPollTimer = null;
  let resizeObs     = null;

  // ------------------------------------------------------------------
  // Canvas sizing — kept in sync with the displayed <img> via ResizeObserver
  // ------------------------------------------------------------------
  function syncCanvasSize() {
    if (!overlay || !feedImg) return;
    const r = feedImg.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) {
      overlay.width  = r.width;
      overlay.height = r.height;
    }
  }

  // ------------------------------------------------------------------
  // Box polling — called every ~200 ms when camera is active
  // ------------------------------------------------------------------
  async function pollBoxes() {
    if (!overlay || !octx) return;
    try {
      const res  = await fetch(`/api/live_boxes/${moduleName}`);
      const data = await res.json();
      syncCanvasSize();
      _drawBoxes(octx, data.boxes, data.width, data.height,
                 overlay.width, overlay.height);
    } catch (_) {}
  }

  // ------------------------------------------------------------------
  // setFeed — show/hide video + start/stop polling
  // ------------------------------------------------------------------
  function setFeed(on) {
    if (on) {
      if (useRawFeed) {
        feedImg.src = `/raw_feed/${moduleName}?t=${Date.now()}`;
      } else {
        feedImg.src = `/video_feed/${moduleName}?t=${Date.now()}`;
      }
      feedImg.classList.remove("hidden");
      placeholder && placeholder.classList.add("hidden");
      liveBadge  && liveBadge.classList.remove("hidden");
      toggleBtn.textContent = "Stop Camera";
      toggleBtn.classList.remove("bg-emerald-600", "hover:bg-emerald-700");
      toggleBtn.classList.add("bg-red-600", "hover:bg-red-700");

      if (overlay) {
        overlay.classList.remove("hidden");
        // Sync once immediately, then watch for resize
        feedImg.onload = syncCanvasSize;
        if (window.ResizeObserver) {
          resizeObs = new ResizeObserver(syncCanvasSize);
          resizeObs.observe(feedImg);
        }
        if (useRawFeed) {
          if (boxesPollTimer) clearInterval(boxesPollTimer);
          boxesPollTimer = setInterval(pollBoxes, 200);
        }
      }
    } else {
      feedImg.removeAttribute("src");
      feedImg.classList.add("hidden");
      placeholder && placeholder.classList.remove("hidden");
      liveBadge  && liveBadge.classList.add("hidden");
      toggleBtn.textContent = "Start Camera";
      toggleBtn.classList.remove("bg-red-600", "hover:bg-red-700");
      toggleBtn.classList.add("bg-emerald-600", "hover:bg-emerald-700");

      if (overlay) {
        overlay.classList.add("hidden");
        octx && octx.clearRect(0, 0, overlay.width, overlay.height);
        if (boxesPollTimer) { clearInterval(boxesPollTimer); boxesPollTimer = null; }
        if (resizeObs) { resizeObs.disconnect(); resizeObs = null; }
      }
    }
  }

  // Initial state
  setFeed(initialActive);

  // ------------------------------------------------------------------
  // Event listeners
  // ------------------------------------------------------------------
  toggleBtn.addEventListener("click", async () => {
    const res  = await fetch(`/api/toggle/${moduleName}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const data = await res.json();
    setFeed(data.active);
  });

  if (uploadInput) {
    uploadInput.addEventListener("change", async () => {
      if (!uploadInput.files.length) return;
      const fd = new FormData();
      fd.append("video", uploadInput.files[0]);
      toggleBtn.disabled = true;
      const res  = await fetch(`/api/upload/${moduleName}`, { method: "POST", body: fd });
      const data = await res.json();
      toggleBtn.disabled = false;
      setFeed(data.active);
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  tickClock();
  setInterval(tickClock, 1000);
});
