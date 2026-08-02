function initModule(moduleName, opts = {}) {
  const feedImg = document.getElementById("feed-img");
  const placeholder = document.getElementById("feed-placeholder");
  const liveBadge = document.getElementById("live-badge");
  const toggleBtn = document.getElementById("toggle-btn");
  const resetBtn = document.getElementById("reset-btn");
  const uploadForm = document.getElementById("upload-form");
  const uploadInput = document.getElementById("upload-input");

  let active = opts.initialActive || false;

  function setFeed(on) {
    if (on) {
      feedImg.src = `/video_feed/${moduleName}?t=${Date.now()}`;
      feedImg.style.display = "block";
      placeholder.style.display = "none";
      liveBadge.classList.add("on");
      toggleBtn.textContent = "Stop Camera";
      toggleBtn.classList.remove("btn-primary");
      toggleBtn.classList.add("btn-danger");
    } else {
      feedImg.removeAttribute("src");
      feedImg.style.display = "none";
      placeholder.style.display = "block";
      liveBadge.classList.remove("on");
      toggleBtn.textContent = "Start Camera";
      toggleBtn.classList.remove("btn-danger");
      toggleBtn.classList.add("btn-primary");
    }
  }

  setFeed(active);

  toggleBtn.addEventListener("click", async () => {
    const res = await fetch(`/api/toggle/${moduleName}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    active = data.active;
    setFeed(active);
  });

  if (resetBtn) {
    resetBtn.addEventListener("click", async () => {
      await fetch(`/api/reset/${moduleName}`, { method: "POST" });
      refreshCounts();
    });
  }

  if (uploadForm) {
    uploadForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!uploadInput.files.length) return;
      const fd = new FormData();
      fd.append("video", uploadInput.files[0]);
      toggleBtn.disabled = true;
      const res = await fetch(`/api/upload/${moduleName}`, { method: "POST", body: fd });
      const data = await res.json();
      toggleBtn.disabled = false;
      active = data.active;
      setFeed(active);
    });
  }

  async function refreshCounts() {
    try {
      const res = await fetch(`/api/counts/${moduleName}`);
      const data = await res.json();
      if (opts.onCounts) opts.onCounts(data);
    } catch (e) { /* silent */ }
  }

  if (opts.onCounts) {
    refreshCounts();
    setInterval(refreshCounts, 2500);
  }
}
