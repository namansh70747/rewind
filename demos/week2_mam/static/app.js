/* Month-1 mam console — wired to flightrecorder via /api/demo + /api/live */

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
  renderGates();
  renderMilestones();
  renderTimeline("good", demo.good, demo.divergence.index);
  renderTimeline("failed", demo.failed, demo.divergence.index);
  renderStore();
  renderBisect();
  renderProof(demo.verify, demo.tamper);
  renderSpikes();
  renderCorpus();
  document.getElementById("run-ids").textContent =
    "good " + demo.good.id + " · failed " + demo.failed.id;
}

function renderGates() {
  const root = document.getElementById("gates");
  root.innerHTML = "";
  const m1 = demo.month1 || {};
  const gates = m1.gates || {};
  ["M0", "M1"].forEach((key) => {
    const g = gates[key];
    if (!g) return;
    const el = document.createElement("article");
    el.className = "gate";
    const rows = (g.criteria || [])
      .map(
        (c) =>
          '<li data-status="' +
          c.status +
          '"><span class="gid">' +
          escapeHtml(c.id) +
          '</span> ' +
          escapeHtml(c.text) +
          ' <em>' +
          (c.status === "pass" ? "PASS" : "FAIL") +
          "</em></li>"
      )
      .join("");
    el.innerHTML =
      '<p class="wk">' +
      key +
      '</p><h3>' +
      escapeHtml(g.title) +
      '</h3><ul class="gate-list">' +
      rows +
      "</ul>";
    root.appendChild(el);
  });
  const banner = document.createElement("article");
  banner.className = "gate gate-status";
  banner.dataset.status = m1.status || "fail";
  banner.innerHTML =
    '<p class="wk">Month 1</p><h3>' +
    (m1.status === "pass" ? "COMPLETE" : "INCOMPLETE") +
    '</h3><p class="ev">Weeks ' +
    escapeHtml(m1.weeks || "1–4") +
    " · corpus " +
    ((m1.corpus && m1.corpus.faithfulness_pct) || "—") +
    "% faithful</p>";
  root.appendChild(banner);
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
    "</p><p class='muted'>Final hash-chain value. CLI: <code>fr record -- python agent.py</code></p></article>";
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

function renderSpikes() {
  const root = document.getElementById("spike-grid");
  const spikes = (demo.month1 && demo.month1.spikes) || [];
  root.innerHTML = spikes
    .map(
      (s) =>
        '<article class="spike" data-status="' +
        s.status +
        '"><p class="wk">Spike ' +
        escapeHtml(s.id) +
        '</p><h3>' +
        escapeHtml(s.title) +
        '</h3><p class="ev">' +
        escapeHtml(s.evidence) +
        '</p><span class="badge">' +
        (s.status === "pass" ? "PASS" : "FAIL") +
        "</span></article>"
    )
    .join("");
}

function renderCorpus() {
  const c = (demo.month1 && demo.month1.corpus) || {};
  document.getElementById("corpus-head").innerHTML =
    "<strong>Faithfulness " +
    (c.faithfulness_pct ?? "—") +
    "%</strong><span class='muted'>" +
    (c.passed ?? 0) +
    "/" +
    (c.n_fixtures ?? 0) +
    " fixtures · verify " +
    (c.verify_n_each ?? "—") +
    "× each · kill-switch on</span>";
  const rows = (c.fixtures || [])
    .map(
      (f) =>
        "<tr><td>" +
        escapeHtml(f.city) +
        "</td><td>" +
        f.boundaries +
        "</td><td>" +
        (f.passed ? "PASS" : "FAIL") +
        "</td><td class='mono'>" +
        escapeHtml(f.run_id || "") +
        "</td></tr>"
    )
    .join("");
  document.getElementById("corpus-table").innerHTML =
    "<table><thead><tr><th>City</th><th>Boundaries</th><th>Verify</th><th>Run</th></tr></thead><tbody>" +
    rows +
    "</tbody></table>";
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

document.getElementById("btn-live").addEventListener("click", async () => {
  const btn = document.getElementById("btn-live");
  const city = document.getElementById("live-city").value.trim() || "Mumbai";
  const box = document.getElementById("live-results");
  btn.disabled = true;
  btn.textContent = "Recording…";
  box.innerHTML = "<p class='muted'>Capturing live Open-Meteo + LLM boundary…</p>";
  try {
    const res = await fetch("/api/live", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ city: city, verify_n: 25 }),
    });
    const data = await res.json();
    if (!data.ok) {
      box.innerHTML =
        "<p class='fail-line'>Live record failed</p><p class='muted'>" +
        escapeHtml(data.error || "unknown") +
        "</p><pre class='log'>" +
        escapeHtml(data.log || "") +
        "</pre>";
      return;
    }
    const steps = (data.steps || [])
      .map(
        (s) =>
          "<li><span class='step-num'>#" +
          s.seq +
          "</span> <span class='step-kind'>" +
          escapeHtml(s.kind) +
          "</span> <span class='mono'>" +
          escapeHtml(s.key) +
          "</span></li>"
      )
      .join("");
    const ev = (data.events || [])
      .slice(0, 12)
      .map((e) => escapeHtml(e.event + " · " + (e.host || e.url || "")))
      .join("\n");
    box.innerHTML =
      "<div class='live-grid'>" +
      "<article><p class='aside-label'>Result</p>" +
      "<p class='stat'>" +
      (data.verify && data.verify.passed ? "VERIFIED" : "FAILED") +
      "</p><p class='muted'>" +
      escapeHtml(data.advice || "") +
      "</p>" +
      "<p class='muted'>run <code>" +
      escapeHtml(data.run_id) +
      "</code> · " +
      data.n_boundaries +
      " boundaries · LLM=" +
      escapeHtml(data.llm_mode) +
      " · network=" +
      escapeHtml(data.network_mode || "") +
      "</p>" +
      (data.probe_note
        ? "<p class='muted'>" + escapeHtml(data.probe_note) + "</p>"
        : "") +
      "<p class='muted'>verify " +
      (data.verify ? data.verify.n + "/" + data.verify.n : "—") +
      " · " +
      escapeHtml((data.verify && data.verify.detail) || "") +
      "</p>" +
      "<p class='mono tiny'>" +
      escapeHtml(data.cli || "") +
      "</p></article>" +
      "<article><p class='aside-label'>Boundaries</p><ol class='live-steps'>" +
      steps +
      "</ol>" +
      "<pre class='log'>" +
      ev +
      "</pre></article></div>";
  } finally {
    btn.disabled = false;
    btn.textContent = "Record live run";
  }
});

loadDemo().catch((err) => {
  document.getElementById("story-title").textContent = "Could not load demo";
  document.getElementById("story-task").textContent = String(err);
});
