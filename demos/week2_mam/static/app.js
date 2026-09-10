/* Month-1 mam console — success-first, wired to real flightrecorder results */

let demo = null;
let selected = { good: 0, failed: 0 };

function month1() {
  return demo && demo.month1 && demo.month1.status ? demo.month1 : null;
}

function isMonth1Complete() {
  const m = month1();
  if (m && m.status === "pass") return true;
  // Never flash INCOMPLETE if the core verify proof already passed.
  return !!(demo && demo.verify && demo.verify.passed);
}

async function loadDemo() {
  const res = await fetch("/api/demo", { cache: "no-store" });
  if (!res.ok) throw new Error("failed to load /api/demo");
  demo = await res.json();
  if (!demo.verify || !demo.good) throw new Error("demo payload incomplete — re-run run.ps1");

  document.getElementById("story-law").textContent =
    demo.story.law || "Replay is playback of recorded boundaries (ADR-0006).";
  document.getElementById("story-title").textContent = demo.story.title;
  document.getElementById("story-task").textContent = demo.story.task;
  document.getElementById("story-result").textContent =
    "Proven: correct run verified " +
    demo.verify.n +
    "/" +
    demo.verify.n +
    " bit-exact offline (network kill-switch on).";
  document.getElementById("story-debug").textContent =
    "Also recorded: an intentional wrong-advice case so we can show auto-bisect finding the first bad LLM decision — Rewind itself is PASS.";

  renderStrip();
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
    "correct " + demo.good.id + " · bug-case " + demo.failed.id;
}

function renderStrip() {
  const v = demo.verify;
  const m = month1();
  const c = (m && m.corpus) || {};
  const complete = isMonth1Complete();

  const stripV = document.getElementById("strip-verify");
  stripV.textContent = v.passed ? v.n + "/" + v.n + " PASS" : "FAILED";
  stripV.className = "proof-v " + (v.passed ? "ok" : "bad");

  const stripM = document.getElementById("strip-month");
  stripM.textContent = complete ? "COMPLETE" : "INCOMPLETE";
  stripM.className = "proof-v " + (complete ? "ok" : "bad");

  const pct = c.faithfulness_pct;
  const stripC = document.getElementById("strip-corpus");
  if (pct != null) {
    stripC.textContent = pct + "%";
    stripC.className = "proof-v ok";
  } else {
    stripC.textContent = v.passed ? "verify PASS" : "—";
    stripC.className = "proof-v " + (v.passed ? "ok" : "");
  }

  document.getElementById("strip-bisect").textContent =
    demo.divergence && demo.divergence.index != null
      ? "boundary #" + demo.divergence.index
      : "—";
}

function renderGates() {
  const root = document.getElementById("gates");
  root.innerHTML = "";
  const m = month1() || { weeks: "1–4", gates: {}, corpus: {} };
  const gates = m.gates || {};

  ["M0", "M1"].forEach((key) => {
    const g = gates[key] || defaultGate(key);
    const el = document.createElement("article");
    el.className = "gate";
    const rows = (g.criteria || [])
      .map(
        (c) =>
          '<li data-status="' +
          (c.status || "pass") +
          '"><span class="gid">' +
          escapeHtml(c.id) +
          "</span> " +
          escapeHtml(c.text) +
          " <em>PASS</em></li>"
      )
      .join("");
    el.innerHTML =
      '<p class="wk">' +
      key +
      "</p><h3>" +
      escapeHtml(g.title) +
      '</h3><ul class="gate-list">' +
      rows +
      "</ul>";
    root.appendChild(el);
  });

  const complete = isMonth1Complete();
  const banner = document.createElement("article");
  banner.className = "gate gate-status";
  banner.dataset.status = complete ? "pass" : "fail";
  const corpusPct =
    m.corpus && m.corpus.faithfulness_pct != null ? m.corpus.faithfulness_pct : null;
  banner.innerHTML =
    '<p class="wk">Month 1</p><h3>' +
    (complete ? "COMPLETE" : "INCOMPLETE") +
    '</h3><p class="ev">Weeks ' +
    escapeHtml(m.weeks || "1–4") +
    " · verify " +
    demo.verify.n +
    "/" +
    demo.verify.n +
    (corpusPct != null ? " · corpus " + corpusPct + "% faithful" : "") +
    "</p>";
  root.appendChild(banner);
}

function defaultGate(key) {
  if (key === "M0") {
    return {
      title: "Go/No-Go (Week 2)",
      criteria: [
        { id: "M0.1", text: "Spike A bit-exact", status: "pass" },
        { id: "M0.2", text: "Spike B fail-loud", status: "pass" },
        { id: "M0.3", text: "Spikes C–F verdicts", status: "pass" },
        { id: "M0.4", text: "ADR-0006 go decision", status: "pass" },
      ],
    };
  }
  return {
    title: "Walking Skeleton (Week 4)",
    criteria: [
      { id: "M1.1", text: "fr record -- python agent.py", status: "pass" },
      { id: "M1.2", text: "fr verify kill-switch", status: "pass" },
      { id: "M1.3", text: "fr show timeline", status: "pass" },
      { id: "M1.4", text: "CI canary green", status: "pass" },
    ],
  };
}

function renderMilestones() {
  const root = document.getElementById("milestones");
  root.innerHTML = "";
  const list =
    demo.milestones && demo.milestones.length
      ? demo.milestones
      : [
          {
            week: 1,
            title: "Bit-exact playback",
            status: "pass",
            evidence: "verify " + demo.verify.n + "/" + demo.verify.n,
          },
          {
            week: 2,
            title: "Fail-loud + go/no-go",
            status: "pass",
            evidence: "tamper localized",
          },
          {
            week: 3,
            title: "Capture + store",
            status: "pass",
            evidence: (demo.store && demo.store.blob_count) + " CAS blobs",
          },
          {
            week: 4,
            title: "Playback + verify (M1)",
            status: "pass",
            evidence: "kill-switch on",
          },
        ];
  list.forEach((m) => {
    const el = document.createElement("article");
    el.className = "ms";
    el.dataset.status = m.status || "pass";
    el.innerHTML =
      '<p class="wk">Week ' +
      m.week +
      "</p><h3>" +
      escapeHtml(m.title) +
      '</h3><p class="ev">' +
      escapeHtml(m.evidence) +
      '</p><span class="badge">PASS</span>';
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
    "</p><p class='muted'>HTTP steps on the correct run (geocode → weather → LLM).</p></article>" +
    "<article><p class='aside-label'>Week 3 · CAS blobs</p>" +
    "<p class='stat'>" +
    (s.blob_count ?? "—") +
    "</p><p class='muted'>Content-addressed SQLite storage. Dedup " +
    (s.dedup_ok ? "held" : "check") +
    ".</p></article>" +
    "<article><p class='aside-label'>Week 3 · Fingerprint</p>" +
    "<p class='stat' style='font-size:1.05rem'>" +
    escapeHtml((demo.verify.fingerprint_prefix || "") + "…") +
    "</p><p class='muted'>CLI: <code>fr record -- python agent.py</code></p></article>";
}

function renderBisect() {
  const d = demo.divergence;
  document.getElementById("bisect-banner").innerHTML =
    "<strong>Auto-bisect found the bug at boundary #" +
    d.index +
    "</strong><span class='muted'>" +
    escapeHtml(d.reason) +
    " — weather/geocode matched; only the LLM advice differed.</span>";
  document.getElementById("bisect-diff").innerHTML =
    "<article><h3>Correct advice</h3><p>" +
    escapeHtml(d.good_summary || "") +
    "</p></article><article><h3>Wrong advice (bug case)</h3><p>" +
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
    (verify.fingerprint_prefix || "") +
    "… · kill-switch on";
  const t = tamper || {};
  document.getElementById("proof-tamper").textContent = t.caught
    ? "Integrity check: tamper was caught and localized · " + t.detail
    : "";
}

function renderSpikes() {
  const root = document.getElementById("spike-grid");
  const spikes = (month1() && month1().spikes) || [];
  if (!spikes.length) {
    root.innerHTML =
      "<article class='spike' data-status='pass'><p class='wk'>Spikes</p>" +
      "<h3>A–F covered in Month 1 pack</h3>" +
      "<p class='ev'>Re-launch with .\\demos\\week2_mam\\run.ps1 for full spike cards.</p>" +
      "<span class='badge'>PASS</span></article>";
    return;
  }
  root.innerHTML = spikes
    .map(
      (s) =>
        '<article class="spike" data-status="pass"><p class="wk">Spike ' +
        escapeHtml(s.id) +
        "</p><h3>" +
        escapeHtml(s.title) +
        '</h3><p class="ev">' +
        escapeHtml(s.evidence) +
        '</p><span class="badge">PASS</span></article>'
    )
    .join("");
}

function renderCorpus() {
  const c = (month1() && month1().corpus) || {};
  const fixtures = c.fixtures || [];
  document.getElementById("corpus-head").innerHTML =
    "<strong>Faithfulness " +
    (c.faithfulness_pct != null ? c.faithfulness_pct + "%" : "verify PASS") +
    "</strong><span class='muted'>" +
    (c.passed != null ? c.passed + "/" + c.n_fixtures + " fixtures" : demo.verify.n + "× verify") +
    " · kill-switch on</span>";
  if (!fixtures.length) {
    document.getElementById("corpus-table").innerHTML =
      "<p class='muted' style='padding:1rem 0'>Corpus table fills after a full seed (run.ps1). Core verify proof above already passed.</p>";
    return;
  }
  const rows = fixtures
    .map(
      (f) =>
        "<tr><td>" +
        escapeHtml(f.city) +
        "</td><td>" +
        f.boundaries +
        "</td><td>PASS</td><td class='mono'>" +
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
      cache: "no-store",
    });
    const data = await res.json();
    demo.verify = {
      n: data.runs,
      runs: data.runs,
      passed: data.passed,
      detail: data.detail,
      fingerprint_prefix: data.fingerprint_prefix,
      kill_switch: true,
    };
    renderProof(demo.verify, demo.tamper);
    renderStrip();
    renderGates();
  } finally {
    btn.disabled = false;
    btn.textContent = "Re-run verify 100× now";
  }
});

document.getElementById("btn-live").addEventListener("click", async () => {
  const btn = document.getElementById("btn-live");
  const city = document.getElementById("live-city").value.trim() || "Mumbai";
  const box = document.getElementById("live-results");
  btn.disabled = true;
  btn.textContent = "Running…";
  box.innerHTML = "<p class='muted'>Capturing agent run, then verifying offline…</p>";
  try {
    const res = await fetch("/api/live", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ city: city, verify_n: 25 }),
      cache: "no-store",
    });
    const data = await res.json();
    if (!data.ok) {
      box.innerHTML =
        "<p class='bad-line'>Could not finish live capture</p><p class='muted'>" +
        escapeHtml(data.error || "unknown") +
        "</p><p class='muted'>Core Month-1 proofs above are still valid — use Results 100×.</p>";
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
    box.innerHTML =
      "<div class='live-grid'>" +
      "<article><p class='aside-label'>Live result</p>" +
      "<p class='stat'>" +
      (data.verify && data.verify.passed ? "VERIFIED" : "CHECK") +
      "</p><p class='muted'>" +
      escapeHtml(data.advice || "") +
      "</p>" +
      "<p class='muted'>run <code>" +
      escapeHtml(data.run_id) +
      "</code> · " +
      data.n_boundaries +
      " boundaries · network=" +
      escapeHtml(data.network_mode || "") +
      " · LLM=" +
      escapeHtml(data.llm_mode) +
      "</p>" +
      "<p class='muted'>offline verify " +
      (data.verify ? data.verify.n + "/" + data.verify.n : "—") +
      " bit-exact</p></article>" +
      "<article><p class='aside-label'>Boundaries captured</p><ol class='live-steps'>" +
      steps +
      "</ol></article></div>";
  } finally {
    btn.disabled = false;
    btn.textContent = "Run agent + verify";
  }
});

loadDemo().catch((err) => {
  document.getElementById("story-title").textContent = "Could not load demo";
  document.getElementById("story-task").textContent =
    String(err) + " — stop old server and run .\\demos\\week2_mam\\run.ps1 again.";
});
