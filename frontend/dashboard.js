/* ============================================================
   dashboard.js — ClassifierBT.com
   ============================================================ */

window.addEventListener("DOMContentLoaded", async () => {
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.href = "/index.html";
    return;
  }
  await loadUserInfo();
  await loadStatistics();
  await loadHistory();
  initUpload();
  document.getElementById("logoutBtn")?.addEventListener("click", logout);
});

// ── User ─────────────────────────────────────────────────────
async function loadUserInfo() {
  try {
    const res = await fetch("/api/auth/me", {
      headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
    });
    if (!res.ok) throw new Error();
    const user = await res.json();
    const display = user.username || user.email;

    // Capitalize first letter
    const formattedName = display
      ? display.charAt(0).toUpperCase() + display.slice(1)
      : "";

    setText("userEmail", display);
    setText("welcomeName", display);
  } catch {
    logout();
  }
}

// ── Statistics ───────────────────────────────────────────────
async function loadStatistics() {
  try {
    const res = await fetch("/api/statistics", {
      headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
    });
    if (!res.ok) throw new Error();
    const s = await res.json();
    setText("total-count", s.total_predictions ?? "—");
    setText("tumor-count", s.tumor_detected ?? "—");
    setText("no-tumor-count", s.no_tumor_detected ?? "—");
    setText(
      "avg-confidence",
      s.average_confidence
        ? (s.average_confidence * 100).toFixed(1) + "%"
        : "—",
    );
  } catch {
    ["total-count", "tumor-count", "no-tumor-count", "avg-confidence"].forEach(
      (id) => setText(id, "—"),
    );
  }
}

// ── History ──────────────────────────────────────────────────
async function loadHistory() {
  const container = document.getElementById("history-list");
  if (!container) return;
  container.innerHTML =
    '<p class="text-xs text-slate-400 italic text-center py-10">Loading…</p>';

  try {
    const res = await fetch("/api/predictions?limit=30", {
      headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
    });
    if (!res.ok) throw new Error();
    const { predictions } = await res.json();

    if (!predictions.length) {
      container.innerHTML =
        '<p class="text-xs text-slate-400 italic text-center py-10">No predictions yet.</p>';
      return;
    }

    container.innerHTML = predictions
      .map((pred) => {
        const d = new Date(pred.created_at);
        const date = d.toLocaleString("en-US", {
          month: "short",
          day: "numeric",
          hour: "numeric",
          minute: "2-digit",
        });
        const conf = (pred.confidence_score * 100).toFixed(1) + "%";
        const label = pred.prediction_label;
        const isPos = label === "Tumor";
        const isUnc = label === "Uncertain" || label === "Invalid Input";

        const chipCls = isUnc
          ? "chip chip-unc"
          : isPos
            ? "chip chip-pos"
            : "chip chip-neg";
        const chipTxt = isUnc ? "Uncertain" : isPos ? "Tumor" : "Negative";
        const initCls = isUnc
          ? "h-init h-init--unc"
          : isPos
            ? "h-init h-init--pos"
            : "h-init h-init--neg";

        const base = pred.filename.replace(/\.[^.]+$/, "");
        const words = base.split(/[_\-\s]+/).filter(Boolean);
        const init =
          words.length >= 2
            ? (words[0][0] + words[1][0]).toUpperCase()
            : base.substring(0, 2).toUpperCase();

        return `
        <div class="h-row">
          <div class="${initCls}">${init}</div>
          <div style="flex:1;min-width:0;">
            <div style="display:flex;justify-content:space-between;align-items:baseline;gap:4px;">
              <span class="h-name">${escapeHtml(pred.filename)}</span>
              <span class="h-date">${date}</span>
            </div>
            <div style="display:flex;align-items:center;gap:6px;margin-top:3px;">
              <span class="${chipCls}">${chipTxt}</span>
              <span class="h-conf">${conf}</span>
            </div>
          </div>
        </div>`;
      })
      .join("");
  } catch {
    container.innerHTML =
      '<p class="text-xs text-red-400 italic text-center py-10">Failed to load.</p>';
  }
}

// ── Upload / Predict ─────────────────────────────────────────
function initUpload() {
  const dropZone = document.getElementById("dropZone");
  const dropInner = document.getElementById("dropInner");
  const imageInput = document.getElementById("imageInput");
  const previewSec = document.getElementById("previewSection");
  const imagePreview = document.getElementById("imagePreview");
  const uploadBtn = document.getElementById("uploadBtn");
  const reUploadBtn = document.getElementById("reUploadBtn");
  const resultDisplay = document.getElementById("resultDisplay");
  const placeholder = document.getElementById("placeholderText");
  const predLabel = document.getElementById("predictionLabel");
  const predScore = document.getElementById("predictionScore");
  const confBar = document.getElementById("confidenceBar");

  if (!imageInput) return;

  // Drag & drop
  dropInner?.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropInner.classList.add("drag-over");
  });
  dropInner?.addEventListener("dragleave", () => {
    dropInner.classList.remove("drag-over");
  });
  dropInner?.addEventListener("drop", (e) => {
    e.preventDefault();
    dropInner.classList.remove("drag-over");
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  });

  imageInput.addEventListener("change", () => {
    if (imageInput.files[0]) handleFile(imageInput.files[0]);
  });

  function handleFile(file) {
    imagePreview.src = URL.createObjectURL(file);
    previewSec.classList.remove("hidden");
    dropZone.classList.add("hidden");
    resultDisplay.classList.add("hidden");
    if (placeholder) placeholder.style.display = "block";
  }

  // Reset to drop zone
  reUploadBtn?.addEventListener("click", () => {
    previewSec.classList.add("hidden");
    dropZone.classList.remove("hidden");
    resultDisplay.classList.add("hidden");
    imageInput.value = "";
    imagePreview.src = "";
    if (placeholder) placeholder.style.display = "block";
  });

  // Predict
  uploadBtn?.addEventListener("click", async () => {
    const file = imageInput.files[0];
    if (!file) {
      alert("Please select a file first.");
      return;
    }
    const token = localStorage.getItem("token");

    uploadBtn.disabled = true;
    uploadBtn.innerHTML = `<span class="material-symbols-outlined" style="font-size:1.125rem;">hourglass_top</span> Classifying…`;

    const fd = new FormData();
    fd.append("file", file);

    try {
      const res = await fetch("/api/predict", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      if (res.status === 401) {
        logout();
        return;
      }
      if (!res.ok) throw new Error(`Server error: ${res.status}`);

      const data = await res.json();
      const isPos = data.label === "Tumor";
      const pct = (data.confidence * 100).toFixed(1);

      predLabel.textContent = data.label;
      predLabel.style.color = isPos ? "#ac0031" : "#006a61";
      predScore.textContent = pct + "%";
      predScore.style.color = "#0b1c30";
      confBar.style.width = pct + "%";
      confBar.style.background = isPos ? "#ac0031" : "#006a61";

      resultDisplay.classList.remove("hidden");
      if (placeholder) placeholder.style.display = "none";

      setTimeout(() => {
        loadHistory();
        loadStatistics();
      }, 800);
    } catch (err) {
      alert("Prediction failed: " + err.message);
    } finally {
      uploadBtn.disabled = false;
      uploadBtn.innerHTML = `<span class="material-symbols-outlined" style="font-size:1.125rem;">analytics</span> Predict Classification`;
    }
  });
}

// ── Helpers ──────────────────────────────────────────────────
function logout() {
  localStorage.removeItem("token");
  window.location.href = "/index.html";
}
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}
