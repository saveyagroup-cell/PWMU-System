// ===========================================================================
// TAB SWITCHING
// ===========================================================================
function initTabs() {
  const buttons = document.querySelectorAll(".tab-btn");
  buttons.forEach(btn => {
    btn.addEventListener("click", () => {
      buttons.forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    });
  });
}

// ===========================================================================
// PANEL CONTROLS (start/stop camera, upload video)
// ===========================================================================
function setupPanel(moduleName) {
  const feedImg = document.getElementById(`feed-${moduleName}`);
  const placeholder = document.getElementById(`placeholder-${moduleName}`);
  const liveBadge = document.getElementById(`badge-${moduleName}`);
  const toggleBtn = document.getElementById(`toggle-${moduleName}`);
  const uploadInput = document.getElementById(`upload-${moduleName}`);
  if (!feedImg || !toggleBtn) return;

  function setFeed(on) {
    if (on) {
      feedImg.src = `/video_feed/${moduleName}?t=${Date.now()}`;
      feedImg.classList.remove("hidden");
      placeholder.classList.add("hidden");
      liveBadge.classList.remove("hidden");
      toggleBtn.textContent = "Stop";
      toggleBtn.classList.remove("bg-emerald-600", "hover:bg-emerald-700");
      toggleBtn.classList.add("bg-red-600", "hover:bg-red-700");
    } else {
      feedImg.removeAttribute("src");
      feedImg.classList.add("hidden");
      placeholder.classList.remove("hidden");
      liveBadge.classList.add("hidden");
      toggleBtn.textContent = "Start";
      toggleBtn.classList.remove("bg-red-600", "hover:bg-red-700");
      toggleBtn.classList.add("bg-emerald-600", "hover:bg-emerald-700");
    }
  }

  toggleBtn.addEventListener("click", async () => {
    const res = await fetch(`/api/toggle/${moduleName}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
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
      const res = await fetch(`/api/upload/${moduleName}`, { method: "POST", body: fd });
      const data = await res.json();
      toggleBtn.disabled = false;
      setFeed(data.active);
    });
  }
}

// ===========================================================================
// LIVE CLOCK
// ===========================================================================
function tickClock() {
  const el = document.getElementById("live-clock");
  if (!el) return;
  const now = new Date();
  el.textContent = now.toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true,
  });
}

// ===========================================================================
// KPI + AUDIT LOG (Section 5)
// ===========================================================================
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

async function refreshKpis() {
  try {
    const res = await fetch("/api/kpis");
    const data = await res.json();

    setText("kpi-total-items", data.total_items_detected ?? 0);
    setText("kpi-balance", data.processing_balance ?? 0);
    setText("kpi-vehicle-in", data.vehicle_in ?? 0);
    setText("kpi-vehicle-in-tab", data.vehicle_in ?? 0);
    setText("kpi-vehicle-out-tab", data.vehicle_out ?? 0);
    setText("stage2-revenue", `₹${(data.estimated_revenue_inr ?? 0).toLocaleString("en-IN")}`);

    const alertsEl = document.getElementById("kpi-alerts");
    const alertsBadge = document.getElementById("kpi-alerts-badge");
    const currentAlerts = data.active_alerts ?? 0;
    if (alertsEl) alertsEl.textContent = currentAlerts;

    // Audio alarm trigger — new alert appeared since last check
    if (window.__lastAlertCount !== undefined && currentAlerts > window.__lastAlertCount) {
      const alarmOn = document.getElementById("alarm-toggle");
      if (!alarmOn || alarmOn.checked) playAlarmBeep();
    }
    window.__lastAlertCount = currentAlerts;

    if (alertsBadge) alertsBadge.classList.toggle("hidden", currentAlerts <= 0);

    updateProgressBars("stage1-bars", data.waste_primary_composition, ["#3B82F6", "#94A3B8"]);
    updateProgressBars("stage2-bars", data.waste_composition,
      ["#1E3A8A", "#16A34A", "#DC2626", "#F59E0B", "#0EA5E9", "#7C3AED", "#64748B"]);

    if (compositionChart && data.waste_composition) {
      const entries = Object.entries(data.waste_composition);
      if (entries.length) {
        compositionChart.data.labels = entries.map(([k]) => k);
        compositionChart.data.datasets[0].data = entries.map(([, v]) => v);
        compositionChart.update();
      }
    }
  } catch (e) { /* server still booting models — silent */ }
}

function updateProgressBars(containerId, composition, palette) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const entries = Object.entries(composition || {});
  if (!entries.length) {
    el.innerHTML = `<p class="text-slate-400 text-xs">No detections yet</p>`;
    return;
  }
  const max = Math.max(...entries.map(([, v]) => v), 1);
  el.innerHTML = entries.map(([label, count], i) => `
    <div>
      <div class="flex justify-between text-xs mb-1">
        <span class="font-medium text-slate-600">${label}</span>
        <span class="text-slate-400">${count}</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill" style="width:${(count / max) * 100}%; background:${palette[i % palette.length]}"></div>
      </div>
    </div>`).join("");
}

async function refreshAuditLog() {
  const body = document.getElementById("audit-log-body");
  if (!body) return;
  try {
    const res = await fetch("/api/audit_log");
    const data = await res.json();
    const rows = data.events || [];
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="4" class="text-center text-slate-400 py-6 text-sm">No events logged yet</td></tr>`;
      return;
    }
    body.innerHTML = rows.map(e => `
      <tr class="border-b border-slate-100 last:border-0">
        <td class="py-2.5 px-3 text-sm font-medium text-slate-700">${e.type}</td>
        <td class="py-2.5 px-3 text-sm text-slate-600">${e.detail}</td>
        <td class="py-2.5 px-3 text-sm text-slate-500">${e.time}</td>
        <td class="py-2.5 px-3">
          <span class="px-2.5 py-1 rounded-full text-xs font-semibold ${
            e.status === "Verified"
              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
              : "bg-red-50 text-red-700 border border-red-200"
          }">${e.status}</span>
        </td>
      </tr>`).join("");
  } catch (e) { /* silent */ }
}

// ===========================================================================
// SECTION 1: ANPR TABLE + MANUAL ENTRY + CSV EXPORT
// ===========================================================================
let __anprRows = [];

async function refreshAnprTable() {
  const body = document.getElementById("anpr-body");
  if (!body) return;
  try {
    const res = await fetch("/api/counts/gate");
    const data = await res.json();
    const rows = data.recent_plates || [];
    __anprRows = rows;
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="6" class="text-center text-slate-400 py-6 text-sm">No plates detected yet</td></tr>`;
      return;
    }
    body.innerHTML = rows.map(p => `
      <tr class="border-b border-slate-100 last:border-0">
        <td class="py-2 px-3">${p.url ? `<img src="${p.url}" class="w-14 h-9 object-cover rounded border border-slate-200">` : "—"}</td>
        <td class="py-2 px-3 text-sm font-semibold text-slate-700">${p.plate}</td>
        <td class="py-2 px-3 text-sm text-slate-600">${p.vehicle_type || "—"}</td>
        <td class="py-2 px-3 text-sm text-slate-600">${p.direction || "—"}</td>
        <td class="py-2 px-3 text-sm text-slate-500">${p.time}</td>
        <td class="py-2 px-3 text-xs">${p.source === "manual"
          ? '<span class="px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">Manual</span>'
          : '<span class="px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">Auto</span>'}</td>
      </tr>`).join("");
  } catch (e) { /* silent */ }
}

function downloadCsvBlob(filename, csvText) {
  const blob = new Blob([csvText], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function setupAnprControls() {
  const exportBtn = document.getElementById("export-anpr-csv");
  if (exportBtn) {
    exportBtn.addEventListener("click", () => {
      const header = "Plate,Vehicle Type,Direction,Time,Source\n";
      const body = __anprRows.map(p => `${p.plate},${p.vehicle_type || ""},${p.direction || ""},${p.time},${p.source || "auto"}`).join("\n");
      downloadCsvBlob(`anpr_visible_${Date.now()}.csv`, header + body);
    });
  }

  const dlLogBtn = document.getElementById("dl-log-gate");
  if (dlLogBtn) dlLogBtn.addEventListener("click", () => window.location.href = "/api/report/plate?period=all");

  const dlPdfBtn = document.getElementById("dl-pdf-gate");
  if (dlPdfBtn) dlPdfBtn.addEventListener("click", () => window.location.href = "/api/report_pdf/gate?period=all");

  const manualBtn = document.getElementById("manual-add-btn");
  if (manualBtn) {
    manualBtn.addEventListener("click", async () => {
      const plate = document.getElementById("manual-plate").value.trim();
      if (!plate) { alert("Plate number daalo pehle"); return; }
      const vehicle_type = document.getElementById("manual-vtype").value;
      const direction = document.getElementById("manual-direction").value;
      await fetch("/api/manual_entry", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plate, vehicle_type, direction }),
      });
      document.getElementById("manual-plate").value = "";
      refreshAnprTable();
    });
  }
}

// ===========================================================================
// SECTION 2: STAGE 1 HOURLY CHART
// ===========================================================================
let stage1HourlyChart = null;

function initStage1Chart() {
  const ctx = document.getElementById("stage1-hourly-chart");
  if (!ctx) return;
  stage1HourlyChart = new Chart(ctx, {
    type: "bar",
    data: { labels: [...Array(24).keys()], datasets: [{ label: "Detections", data: Array(24).fill(0), backgroundColor: "#1E3A8A" }] },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
  });
}

async function refreshStage1Chart() {
  if (!stage1HourlyChart) return;
  try {
    const res = await fetch("/api/hourly/waste_primary?period=daily");
    const data = await res.json();
    stage1HourlyChart.data.datasets[0].data = Object.keys(data).sort((a, b) => a - b).map(h => data[h]);
    stage1HourlyChart.update();
  } catch (e) { /* silent */ }
}

// ===========================================================================
// SECTION 3: STAGE 2 PIE CHART
// ===========================================================================
let compositionChart = null;
const PALETTE = ["#1E3A8A", "#16A34A", "#DC2626", "#F59E0B", "#0EA5E9", "#7C3AED", "#64748B"];

function initCompositionChart() {
  const ctx = document.getElementById("stage2-pie-chart");
  if (!ctx) return;
  compositionChart = new Chart(ctx, {
    type: "doughnut",
    data: { labels: ["No data yet"], datasets: [{ data: [1], backgroundColor: ["#E2E8F0"], borderWidth: 0 }] },
    options: { plugins: { legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } } }, cutout: "62%" },
  });
  compositionChart.data.datasets[0].backgroundColor = PALETTE;
}

// ===========================================================================
// SECTION 4: SHED ALERTS TABLE + AUDIO ALARM
// ===========================================================================
async function refreshShedAlerts() {
  const body = document.getElementById("shed-alerts-body");
  if (!body) return;
  try {
    const res = await fetch("/api/counts/thief");
    const data = await res.json();
    const rows = data.recent || [];
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="3" class="text-center text-slate-400 py-6 text-sm">No alerts yet</td></tr>`;
      return;
    }
    body.innerHTML = rows.map(a => `
      <tr class="border-b border-slate-100 last:border-0">
        <td class="py-2 px-3">${a.url ? `<img src="${a.url}" class="w-14 h-9 object-cover rounded border border-slate-200">` : "—"}</td>
        <td class="py-2 px-3 text-sm"><span class="px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-200 text-xs font-semibold">${a.reason}</span></td>
        <td class="py-2 px-3 text-sm text-slate-500">${a.time}</td>
      </tr>`).join("");
  } catch (e) { /* silent */ }
}

let __audioCtx = null;
function playAlarmBeep() {
  try {
    __audioCtx = __audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const o = __audioCtx.createOscillator();
    const g = __audioCtx.createGain();
    o.type = "square"; o.frequency.value = 880;
    g.gain.setValueAtTime(0.15, __audioCtx.currentTime);
    o.connect(g); g.connect(__audioCtx.destination);
    o.start();
    o.frequency.setValueAtTime(660, __audioCtx.currentTime + 0.15);
    o.stop(__audioCtx.currentTime + 0.35);
  } catch (e) { /* browser may block until first user interaction — fine */ }
}

function setupShedControls() {
  const dlLogBtn = document.getElementById("dl-log-thief");
  if (dlLogBtn) dlLogBtn.addEventListener("click", () => window.location.href = "/api/report/thief?period=all");

  const dlPdfBtn = document.getElementById("dl-pdf-thief");
  if (dlPdfBtn) dlPdfBtn.addEventListener("click", () => window.location.href = "/api/report_pdf/thief?period=all");
}

// ===========================================================================
// LOG DOWNLOAD BUTTONS (Stage 1 / Stage 2)
// ===========================================================================
function setupLogDownloadButtons() {
  const s1 = document.getElementById("dl-log-waste_primary");
  if (s1) s1.addEventListener("click", () => window.location.href = "/api/report/waste_primary?period=all");
  const s1pdf = document.getElementById("dl-pdf-waste_primary");
  if (s1pdf) s1pdf.addEventListener("click", () => window.location.href = "/api/report_pdf/waste_primary?period=all");

  const s2 = document.getElementById("dl-log-waste_secondary");
  if (s2) s2.addEventListener("click", () => window.location.href = "/api/report/waste_secondary?period=all");
  const s2pdf = document.getElementById("dl-pdf-waste_secondary");
  if (s2pdf) s2pdf.addEventListener("click", () => window.location.href = "/api/report_pdf/waste_secondary?period=all");
}

// ===========================================================================
// SECTION 5: REPORT GENERATOR
// ===========================================================================
function setupReportGenerator() {
  const btn = document.getElementById("generate-report-btn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const module = document.getElementById("report-module").value;
    const period = document.getElementById("report-period").value;
    const format = document.getElementById("report-format").value;

    let url;
    if (format === "pdf") {
      url = module === "full" ? `/api/report_pdf/full?period=${period}` : `/api/report_pdf/${module}?period=${period}`;
    } else {
      url = module === "full" ? `/api/report/full?period=${period}` : `/api/report/${module}?period=${period}`;
    }
    window.location.href = url;
  });
}

// ===========================================================================
// BOOT
// ===========================================================================
document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  ["gate", "waste_primary", "waste_secondary", "thief"].forEach(setupPanel);
  setupAnprControls();
  setupShedControls();
  setupLogDownloadButtons();
  setupReportGenerator();
  initStage1Chart();
  initCompositionChart();

  tickClock();
  setInterval(tickClock, 1000);

  refreshKpis();
  refreshAuditLog();
  refreshAnprTable();
  refreshStage1Chart();
  refreshShedAlerts();

  setInterval(refreshKpis, 3000);
  setInterval(refreshAuditLog, 4000);
  setInterval(refreshAnprTable, 3000);
  setInterval(refreshStage1Chart, 15000);
  setInterval(refreshShedAlerts, 3000);
});
