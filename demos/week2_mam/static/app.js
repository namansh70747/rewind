/* Week-2 mam demo UI — wired to /api/demo and /api/verify */

let demo = null;
let selected = { good: 0, failed: 0 };

async function loadDemo() {
  const res = await fetch("/api/demo");
  if (!res.ok) throw new Error("failed to load /api/demo");
  demo = await res.json();
  renderStory();
  renderTimeline("good", demo.good, demo.divergence.index);
  renderTimeline("failed", demo.failed, demo.divergence.index);
  renderBisect();
  renderProof(demo.verify);
  document.getElementById("run-ids").textContent =
    `good ${demo.good.id} · failed ${demo.failed.id}`;
}

function renderStory() {
  const s = demo.story;
  document.getElementById("story-title").textContent = s.title;
  document.getElementById("story-task").textContent = s.task;
  document.getElementById("story-failure").textContent =
    `Failed run: ${s.failure_summary}`;
}

function renderTimeline(which, run, divergeIndex) {
  const ol = document.getElementById(`timeline-${which}`);
  ol.innerHTML = "";
  run.steps.forEach((step, i) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.innerHTML =
      `<span class="step-num">#${step.seq}</span> ` +
      `<span class="step-kind">${escapeHtml(step.kind)}</span>` +
      `<span class="step-key">${escapeHtml(step.key)}</span>`;
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
  const el = document.getElementById(`inspect-${which}`);
  el.innerHTML = `
    <h3>Boundary #${step.seq} · ${escapeHtml(step.kind)}:${escapeHtml(step.key)}</h3>
    <dl class="kv">
      <dt>Request</dt>
      <dd>${escapeHtml(step.request_summary || "(none)")}</dd>
    </dl>
    <dl class="kv">
      <dt>Response</dt>
      <dd>${escapeHtml(step.response_summary || "(none)")}</dd>
    </dl>
    <dl class="kv">
      <dt>Chain</dt>
      <dd>${escapeHtml(step.chain_hash)}…</dd>
    </dl>
  `;
}

function renderBisect() {
  const d = demo.divergence;
  const banner = document.getElementById("bisect-banner");
  banner.innerHTML = `
    <strong>First divergence at boundary #${d.index}</strong>
    <span>${escapeHtml(d.reason)}</span>
  `;
  const diff = document.getElementById("bisect-diff");
  diff.innerHTML = `
    <article>
      <h3>Good run</h3>
      <p>${escapeHtml(d.good_summary || "")}</p>
    </article>
    <article>
      <h3>Failed run</h3>
      <p>${escapeHtml(d.failed_summary || "")}</p>
    </article>
  `;
}

function renderProof(verify) {
  const metric = document.getElementById("proof-metric");
  const detail = document.getElementById("proof-detail");
  if (verify.passed) {
    metric.textContent = `BIT-EXACT  ${verify.n}/${verify.n}`;
    metric.style.color = "var(--ok)";
  } else {
    metric.textContent = `FAILED after ${verify.runs} replay(s)`;
    metric.style.color = "var(--danger)";
  }
  detail.textContent =
    `${verify.detail} · fingerprint ${verify.fingerprint_prefix}… · kill-switch on`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

document.querySelectorAll(".act").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".act").forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    const act = btn.dataset.act;
    document.querySelectorAll(".panel").forEach((panel) => {
      panel.classList.toggle("is-hidden", panel.dataset.panel !== act);
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
    renderProof({
      n: data.runs,
      runs: data.runs,
      passed: data.passed,
      detail: data.detail,
      fingerprint_prefix: data.fingerprint_prefix,
    });
  } finally {
    btn.disabled = false;
    btn.textContent = "Re-run verify 100×";
  }
});

loadDemo().catch((err) => {
  document.getElementById("story-title").textContent = "Could not load demo";
  document.getElementById("story-task").textContent = String(err);
});
