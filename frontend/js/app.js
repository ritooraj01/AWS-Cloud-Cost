/* ===================================================
   Cloud Cost Panic Button — Frontend Logic
   =================================================== */

// ---- Backend URL config -----------------------------------------------
// LOCAL DEV:  leave as empty string (uses relative paths, works with uvicorn)
// PRODUCTION: set to your Render backend URL, e.g.:
//   const BACKEND_URL = "https://cloud-cost-panic-button.onrender.com";
const BACKEND_URL = window.BACKEND_URL || "";

// ---- DOM refs -------------------------------------------------------
const csvInput    = document.getElementById("csv-input");
const fileNameEl  = document.getElementById("file-name");
const analyzeBtn  = document.getElementById("analyze-btn");
const dropZone    = document.getElementById("drop-zone");
const uploadError = document.getElementById("upload-error");
const spinner     = document.getElementById("upload-spinner");
const uploadSec   = document.getElementById("upload-section");
const resultsSec  = document.getElementById("results-section");
const resetBtn    = document.getElementById("reset-btn");
const chartsToggle = document.getElementById("charts-toggle");
const chartsBody  = document.getElementById("charts-content");

let selectedFile  = null;
let charts        = {};       // chart instances for destroy-on-reload

// ---- File selection via input or drag-drop --------------------------
csvInput.addEventListener("change", () => handleFile(csvInput.files[0]));

dropZone.addEventListener("click", (e) => {
  // The <label for="csv-input"> already opens the dialog natively.
  // Only trigger manually when the click landed directly on the drop zone
  // background — not on the label, button, or the input itself.
  if (e.target === dropZone || e.target.tagName === "P" || e.target.tagName === "SPAN") {
    csvInput.click();
  }
});

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  const f = e.dataTransfer.files[0];
  if (f) handleFile(f);
});

function handleFile(file) {
  if (!file) return;
  if (!file.name.endsWith(".csv")) {
    showError("Please upload a .csv file.");
    return;
  }
  selectedFile = file;
  fileNameEl.textContent = file.name;
  analyzeBtn.disabled = false;
  hideError();
}

// ---- Analyze button -------------------------------------------------
analyzeBtn.addEventListener("click", async () => {
  if (!selectedFile) return;
  await uploadAndAnalyze(selectedFile);
});

async function uploadAndAnalyze(file) {
  hideError();
  showSpinner(true);
  analyzeBtn.disabled = true;

  const formData = new FormData();
  formData.append("file", file);

  try {
    // Step 1: Upload
    const uploadRes = await fetch(`${BACKEND_URL}/upload`, { method: "POST", body: formData });
    const uploadJson = await uploadRes.json();
    if (!uploadRes.ok) {
      throw new Error(uploadJson.detail || "Upload failed.");
    }

    // Step 2: Fetch analysis
    const analysisRes = await fetch(`${BACKEND_URL}/analysis/${uploadJson.session_id}`);
    const data = await analysisRes.json();
    if (!analysisRes.ok) {
      throw new Error(data.detail || "Analysis failed.");
    }

    renderResults(data);
  } catch (err) {
    showError(err.message);
    analyzeBtn.disabled = false;
  } finally {
    showSpinner(false);
  }
}

// ---- Reset ----------------------------------------------------------
resetBtn.addEventListener("click", () => {
  resultsSec.classList.add("hidden");
  uploadSec.classList.remove("hidden");
  selectedFile = null;
  fileNameEl.textContent = "No file selected";
  analyzeBtn.disabled = true;
  csvInput.value = "";
  destroyCharts();
});

// ---- Charts toggle --------------------------------------------------
chartsToggle.addEventListener("click", () => {
  const arrow = chartsToggle.querySelector(".toggle-arrow");
  const isOpen = !chartsBody.classList.contains("hidden");
  chartsBody.classList.toggle("hidden", isOpen);
  arrow.classList.toggle("open", !isOpen);
});

// =====================================================================
// RENDER RESULTS
// =====================================================================
function renderResults(data) {
  const { summary, top_drivers, spike, waste_signals, suggestions, charts: chartData, meta } = data;

  renderSummaryCard(summary);
  renderDrivers(top_drivers, summary.last_7_days_inr);
  renderSuggestions(suggestions);
  renderSpikeDetail(spike);
  renderWasteSignals(waste_signals);
  renderCharts(chartData);

  uploadSec.classList.add("hidden");
  resultsSec.classList.remove("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ---- ① Summary Card -------------------------------------------------
function renderSummaryCard(s) {
  document.getElementById("s-last7").textContent = `₹${fmt(s.last_7_days_inr)}`;
  document.getElementById("s-prev7").textContent = `₹${fmt(s.previous_7_days_inr)}`;

  const changeEl = document.getElementById("s-change");
  const pct = s.change_pct;
  changeEl.textContent = `${s.trend_emoji} ${s.trend_label}`;
  changeEl.className = "summary-value badge " + (pct > 0 ? "badge-red" : pct < 0 ? "badge-green" : "badge-yellow");

  document.getElementById("s-savings").textContent =
    s.total_potential_savings_inr > 0 ? `💸 ₹${fmt(s.total_potential_savings_inr)}/mo` : "—";

  document.getElementById("s-narrative").textContent = s.narrative;
}

// ---- ② Top 3 Cost Drivers ------------------------------------------
function renderDrivers(drivers, last7Total) {
  const el = document.getElementById("drivers-list");
  el.innerHTML = "";

  if (!drivers || drivers.length === 0) {
    el.innerHTML = `<p style="color:var(--muted);font-size:0.9rem;">
      Not enough data to identify top cost drivers yet (requires 7+ days of history).
    </p>`;
    return;
  }

  drivers.forEach((d) => {
    const isNew = d.category === "new_service";
    const impactLabel = isNew
      ? `₹${fmt(d.impact_amount)} new`
      : d.impact_amount > 0
      ? `+₹${fmt(d.impact_amount)}`
      : `₹${fmt(d.impact_amount)}`;

    const confClass = { HIGH: "conf-high", MEDIUM: "conf-medium", LOW: "conf-low" }[d.confidence] || "";
    const rankEmoji = ["🥇", "🥈", "🥉"][d.rank - 1] || "📌";

    const copyText = d.human_text || d.description || "";

    el.innerHTML += `
      <div class="driver-item rank-${d.rank}">
        <div class="driver-header">
          <span class="driver-rank">${rankEmoji}</span>
          <span class="driver-label">${escHtml(d.description)}</span>
          <span class="driver-impact">${impactLabel}</span>
        </div>
        <p class="driver-human">${escHtml(d.human_text || "")}</p>
        <div class="driver-footer">
          <span class="driver-confidence badge ${confClass}">${d.confidence}</span>
          <button class="btn-copy" onclick="copyText(this, ${JSON.stringify(copyText)})">
            📋 Copy Insight
          </button>
        </div>
      </div>`;
  });
}

// ---- ③ Suggestions --------------------------------------------------
function renderSuggestions(suggestions) {
  const el = document.getElementById("suggestions-list");
  el.innerHTML = "";

  if (!suggestions || suggestions.length === 0) {
    el.innerHTML = `<p style="color:var(--muted);font-size:0.9rem;">No specific actions identified yet.</p>`;
    return;
  }

  suggestions.forEach((s) => {
    const confClass = { HIGH: "conf-high", MEDIUM: "conf-medium", LOW: "conf-low" }[s.confidence] || "";
    const savingsLabel = s.savings_inr > 0 ? `Potential savings up to ₹${fmt(s.savings_inr)}/month` : "Savings vary";

    el.innerHTML += `
      <div class="suggestion-item">
        <div class="suggestion-header">
          <span class="suggestion-action">⚡ ${escHtml(s.action)}</span>
          <span class="suggestion-savings">${savingsLabel}</span>
        </div>
        <p class="suggestion-detail">${escHtml(s.detail)}</p>
        <div class="suggestion-footer">
          <span class="driver-confidence badge ${confClass}">${s.confidence} confidence</span>
          <button class="btn-copy" onclick="copyText(this, ${JSON.stringify(s.copyable_text)})">
            📋 Copy
          </button>
        </div>
      </div>`;
  });
}

// ---- ④ Spike Detail (inside charts section) -------------------------
function renderSpikeDetail(spike) {
  const el = document.getElementById("spike-detail");
  if (!el) return;

  if (spike.insufficient_data) {
    el.innerHTML = `
      <div class="spike-alert no-spike">
        <h4>ℹ️ Spike Detection Unavailable</h4>
        <p>${escHtml(spike.reason)}</p>
      </div>`;
    return;
  }

  if (!spike.detected) {
    el.innerHTML = `
      <div class="spike-alert no-spike">
        <h4>✅ No Unusual Spending Detected</h4>
        <p>${escHtml(spike.reason)}</p>
      </div>`;
    return;
  }

  let affectedHtml = "";
  if (spike.affected_services?.length) {
    affectedHtml = spike.affected_services
      .map(s => `<li><strong>${escHtml(s.service)}</strong>: 
        ${s.change_pct > 0 ? "+" : ""}${s.change_pct}% 
        (₹${fmt(s.change_amount)} extra this week)</li>`)
      .join("");
  }

  el.innerHTML = `
    <div class="spike-alert">
      <h4>🔴 Cost Spike Detected (${spike.overall_change_pct > 0 ? "+" : ""}${spike.overall_change_pct}%)</h4>
      <p>${escHtml(spike.reason)}</p>
      ${affectedHtml ? `<ul style="margin-top:0.6rem;padding-left:1.2rem;font-size:0.88rem;">${affectedHtml}</ul>` : ""}
    </div>`;
}

// ---- Waste Signals --------------------------------------------------
function renderWasteSignals(signals) {
  const el = document.getElementById("waste-signals");
  if (!el || !signals || signals.length === 0) return;

  const confClass = { HIGH: "conf-high", MEDIUM: "conf-medium", LOW: "conf-low" };

  el.innerHTML = `<h3>🗑️ Billing-Based Waste Signals</h3>` +
    signals.map(w => `
      <div class="waste-item">
        <div class="waste-title">
          <span>${escHtml(w.title)}</span>
          <span class="driver-confidence badge ${confClass[w.confidence] || ""}">${w.confidence}</span>
        </div>
        <p class="waste-desc">${escHtml(w.human_text || w.description || "")}</p>
      </div>`).join("");
}

// ---- Charts ---------------------------------------------------------
function renderCharts(chartData) {
  // Charts are inside collapsible; show toggle arrow default open
  chartsBody.classList.remove("hidden");
  chartsToggle.querySelector(".toggle-arrow").classList.add("open");

  destroyCharts();

  const COLORS = ["#e53e3e","#dd6b20","#3182ce","#38a169","#6b46c1","#d69e2e","#00b5d8"];

  // Top Services — Horizontal Bar
  const svcCtx = document.getElementById("chart-services")?.getContext("2d");
  if (svcCtx && chartData.top_services?.length) {
    const labels = chartData.top_services.map(s => s.service);
    const values = chartData.top_services.map(s => scaleInr(s.total_cost, chartData));
    charts.services = new Chart(svcCtx, {
      type: "bar",
      data: {
        labels,
        datasets: [{ label: "Cost (₹)", data: values, backgroundColor: COLORS, borderRadius: 6 }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { x: { ticks: { callback: v => `₹${fmt(v)}` } } },
      },
    });
  }

  // Daily Trend — Line
  const trendCtx = document.getElementById("chart-trend")?.getContext("2d");
  if (trendCtx && chartData.daily_trend?.length) {
    const labels = chartData.daily_trend.map(d => d.date.slice(5)); // MM-DD
    const values = chartData.daily_trend.map(d => scaleInr(d.cost, chartData));
    charts.trend = new Chart(trendCtx, {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "Daily Cost (₹)", data: values,
          borderColor: "#e53e3e", backgroundColor: "rgba(229,62,62,0.08)",
          tension: 0.35, fill: true, pointRadius: 3,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { ticks: { callback: v => `₹${fmt(v)}` } } },
      },
    });
  }

  // Region Breakdown — Doughnut
  const regCtx = document.getElementById("chart-regions")?.getContext("2d");
  if (regCtx && chartData.region_breakdown?.length) {
    const labels = chartData.region_breakdown.map(r => r.region);
    const values = chartData.region_breakdown.map(r => scaleInr(r.total_cost, chartData));
    charts.regions = new Chart(regCtx, {
      type: "doughnut",
      data: {
        labels,
        datasets: [{ label: "Cost (₹)", data: values, backgroundColor: COLORS, borderWidth: 2 }],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: "bottom", labels: { font: { size: 11 } } },
          tooltip: { callbacks: { label: ctx => ` ₹${fmt(ctx.parsed)}` } },
        },
      },
    });
  }
}

// Scale cost values to INR.
// Heuristic: compute average daily cost per service. Real INR bills will
// have values in hundreds per day; USD bills typically < $10/service/day.
function scaleInr(amount, chartData) {
  const total  = chartData.top_services?.reduce((a, b) => a + b.total_cost, 0) || 0;
  const days   = chartData.daily_trend?.length || 14;
  const svcs   = chartData.top_services?.length || 1;
  const avgDailyPerSvc = total / days / svcs;
  return avgDailyPerSvc < 10 ? Math.round(amount * 83) : Math.round(amount);
}

function destroyCharts() {
  Object.values(charts).forEach(c => c?.destroy());
  charts = {};
}

// =====================================================================
// UTILITIES
// =====================================================================
function fmt(n) {
  return Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

function escHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function showError(msg) {
  uploadError.textContent = "⚠️ " + msg;
  uploadError.classList.remove("hidden");
}
function hideError() { uploadError.classList.add("hidden"); }
function showSpinner(v) { spinner.classList.toggle("hidden", !v); }

// ---- Copy to Clipboard (viral share feature) -------------------------
window.copyText = function (btn, text) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = "✅ Copied!";
    btn.classList.add("copied");
    setTimeout(() => {
      btn.textContent = orig;
      btn.classList.remove("copied");
    }, 2000);
  });
};
