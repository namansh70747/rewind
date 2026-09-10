/* Weeks 1–4 mam demo — wired to flightrecorder via /api/demo */

let demo = null;
let selected = { good: 0, failed: 0 };

async function loadDemo() {
  const res = await fetch("/api/demo");
  if (!res.ok) throw new Error("failed to load /api/demo");
  demo = await res.json();
  document.getElementById("story-law").textContent = demo.story.law || "";
  document.getElementById("story-title").textContent = demo.story.title;
  document.getElementById("story-task").textContent = demo.story.task;
  document.getElementById("story-failure").textContent =
    "Failed run: " + demo.story.failure_summary;
  renderMilestones();
  renderTimeline("good", demo.good, demo.divergence.index);
  renderTimeline("failed", demo.failed, demo.divergence.index);
  renderStore();
  renderBisect();
  renderProof(demo.verify, demo.tamper);
  document.getElementById("run-ids").textContent =
    "good " + demo.good.id + " · failed " + demo.failed.id;
}

function renderMilestones() {
  const root = document.getElementById("milestones");
  root.innerHTML = "";
  (demo.milestones || []).forEach((m) => {
    const el = document.createElement("article");
    el.className = "ms";
    el.dataset.status = m.status;
    el.innerHTML =
      '<p class="wk">Week ' +
      m.week +
      "</p><h3>" +
      escapeHtml(m.title) +
      '</h3><p class="ev">' +
      escapeHtml(m.evidence) +
      '</p><span class="badge">' +
      (m.status === "pass" ? "PASS" : "FAIL") +
      "</span>";
    root.appendChild(el);
  });
}

function renderTimeline(which, run, divergeIndex) {
  const ol = document.getElementById("timeline-" + which);
  ol.innerHTML = "";
  run.steps.forEach((step, i) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.innerHTML =
      '<span class="step-num">#' +
      step.seq +
      '</span><span class="step-kind">' +
      escapeHtml(step.kind) +
      '</span><span class="step-key">' +
      escapeHtml(step.key) +
      "</span>";
    if (i === divergeIndex) btn.classList.add("is-diverge");
    if (i === selected[which]) btn.classList.add("is-active");
    btn.addEventListener("click", () => {
      selected[which] = i;
      renderTimeline(which, run, divergeIndex);
      renderInspect(which, run.steps[i]);
    });
    li.appendChild(btn);
    ol.appendChild(li);
  });
  renderInspect(which, run.steps[selected[which]]);
}

function renderInspect(which, step) {
  const el = document.getElementById("inspect-" + which);
  el.innerHTML =
    "<h3>Boundary #" +
    step.seq +
    " · " +
    escapeHtml(step.kind) +
    ":" +
    escapeHtml(step.key) +
    "</h3>" +
    '<dl class="kv"><dt>Request</dt><dd>' +
    escapeHtml(step.request_summary || "(none)") +
    "</dd></dl>" +
    '<dl class="kv"><dt>Response</dt><dd>' +
    escapeHtml(step.response_summary || "(none)") +
    "</dd></dl>" +
    '<dl class="kv"><dt>Hash-chain link</dt><dd>' +
    escapeHtml(step.chain_hash) +
    "…</dd></dl>";
}

function renderStore() {
  const s = demo.store || {};
  const g = demo.good;
  document.getElementById("store-grid").innerHTML =
    "<article><p class='aside-label'>Week 3 · Boundaries</p>" +
    "<p class='stat'>" +
    g.n_boundaries +
    "</p><p class='muted'>HTTP steps captured for the good run (geocode, weather, LLM).</p></article>" +
    "<article><p class='aside-label'>Week 3 · CAS blobs</p>" +
    "<p class='stat'>" +
    (s.blob_count ?? "—") +
    "</p><p class='muted'>Content-addressed payloads in SQLite. Dedup after identical re-save: " +
    (s.dedup_ok ? "held" : "check failed") +
    " (" +
    (s.blob_count_after_identical_resave ?? "—") +
    ").</p></article>" +
    "<article><p class='aside-label'>Week 3 · Fingerprint</p>" +
    "<p class='stat' style='font-size:1.05rem'>" +
    escapeHtml((demo.verify.fingerprint_prefix || "") + "…") +
    "</p><p class='muted'>Final hash-chain value for the good recording. Provider label: " +
    escapeHtml([g.provider, g.model].filter(Boolean).join("/") || "unlabeled") +
    ".</p></article>";
}

function renderBisect() {
  const d = demo.divergence;
  document.getElementById("bisect-banner").innerHTML =
    "<strong>First divergence at boundary #" +
    d.index +
    "</strong><span class='muted'>" +
    escapeHtml(d.reason) +
    "</span>";
  document.getElementById("bisect-diff").innerHTML =
    "<article><h3>Good run</h3><p>" +
    escapeHtml(d.good_summary || "") +
    "</p></article><article><h3>Failed run</h3><p>" +
    escapeHtml(d.failed_summary || "") +
    "</p></article>";
}

function renderProof(verify, tamper) {
  const metric = document.getElementById("proof-metric");
  if (verify.passed) {
    metric.textContent = "BIT-EXACT  " + verify.n + "/" + verify.n;
    metric.style.color = "var(--ok)";
  } else {
    metric.textContent = "FAILED after " + verify.runs + " replay(s)";
    metric.style.color = "var(--bad)";
  }
  document.getElementById("proof-detail").textContent =
    verify.detail +
    " · fingerprint " +
    verify.fingerprint_prefix +
    "… · kill-switch " +
    (verify.kill_switch ? "on" : "n/a");
  const t = tamper || {};
  document.getElementById("proof-tamper").textContent = t.caught
    ? "Tamper oracle: caught · " + t.detail
    : "Tamper oracle: not run";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("is-on"));
    btn.classList.add("is-on");
    const act = btn.dataset.act;
    document.querySelectorAll(".stage").forEach((panel) => {
      panel.classList.toggle("is-off", panel.dataset.panel !== act);
    });
  });
});

document.getElementById("btn-verify").addEventListener("click", async () => {
  const btn = document.getElementById("btn-verify");
  btn.disabled = true;
  btn.textContent = "Verifying 100×…";
  try {
    const res = await fetch("/api/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ n: 100 }),
    });
    const data = await res.json();
    renderProof(
      {
        n: data.runs,
        runs: data.runs,
        passed: data.passed,
        detail: data.detail,
        fingerprint_prefix: data.fingerprint_prefix,
        kill_switch: true,
      },
      demo.tamper
    );
  } finally {
    btn.disabled = false;
    btn.textContent = "Run verify 100× again";
  }
});

loadDemo().catch((err) => {
  document.getElementById("story-title").textContent = "Could not load demo";
  document.getElementById("story-task").textContent = String(err);
});
