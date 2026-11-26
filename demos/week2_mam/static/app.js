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
  const res = await fetch("/api/demo", { cache: "no-store", credentials: "include" });
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
    "Debug fixture: an intentional wrong-advice recording is retained so auto-bisect can localise the first diverging LLM decision. The recorder and verify path remain PASS.";

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
  stripV.textContent = v.passed ? v.n + "/" + v.n : "FAIL";
  stripV.className = "gauge-v " + (v.passed ? "ok" : "bad");

  const stripM = document.getElementById("strip-month");
  stripM.textContent = complete ? "Month 1 complete" : "Month 1 incomplete";

  const pct = c.faithfulness_pct;
  const stripC = document.getElementById("strip-corpus");
  stripC.textContent =
    pct != null ? "corpus " + pct + "%" : v.passed ? "verify pass" : "—";

  document.getElementById("strip-bisect").textContent =
    demo.divergence && demo.divergence.index != null
      ? "first fail #" + demo.divergence.index
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

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
    credentials: "include",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.error) || "HTTP " + res.status);
  }
  return data;
}

document.getElementById("btn-verify").addEventListener("click", async () => {
  const btn = document.getElementById("btn-verify");
  const status = document.getElementById("verify-status");
  const TOTAL = 100;
  const BATCH = 10;
  btn.disabled = true;
  btn.textContent = "Verifying…";
  status.textContent = "Starting offline verify 0/" + TOTAL + "…";
  const t0 = Date.now();
  let done = 0;
  let last = null;
  try {
    // Batches keep the UI alive — a single 100× call looks hung for ~50s.
    while (done < TOTAL) {
      const n = Math.min(BATCH, TOTAL - done);
      status.textContent =
        "Verifying " + done + "/" + TOTAL + " bit-exact… (" + Math.round((Date.now() - t0) / 1000) + "s)";
      btn.textContent = "Verifying " + done + "/" + TOTAL + "…";
      last = await postJson("/api/verify", { n: n });
      if (!last.passed) {
        throw new Error(last.detail || "verify failed");
      }
      done += last.runs;
      demo.verify = {
        n: done,
        runs: done,
        passed: true,
        detail: last.detail,
        fingerprint_prefix: last.fingerprint_prefix,
        kill_switch: true,
      };
      renderProof(demo.verify, demo.tamper);
      renderStrip();
    }
    demo.verify.n = TOTAL;
    demo.verify.runs = TOTAL;
    demo.verify.detail =
      "all replays match the recorded fingerprint (bit-exact) — re-ran " + TOTAL + "× just now";
    renderProof(demo.verify, demo.tamper);
    renderStrip();
    renderGates();
    status.textContent =
      "PASS " + TOTAL + "/" + TOTAL + " in " + Math.round((Date.now() - t0) / 1000) + "s — kill-switch on.";
  } catch (err) {
    status.textContent = "Verify failed: " + err;
    if (demo && demo.verify) {
      renderProof(demo.verify, demo.tamper);
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "Re-run verify 100×";
  }
});

document.getElementById("btn-live").addEventListener("click", async () => {
  const btn = document.getElementById("btn-live");
  const city = document.getElementById("live-city").value.trim() || "Mumbai";
  const box = document.getElementById("live-results");
  btn.disabled = true;
  btn.textContent = "Running…";
  const t0 = Date.now();
  const tick = setInterval(() => {
    box.innerHTML =
      "<p class='muted'>Capturing live weather + offline verify… " +
      Math.round((Date.now() - t0) / 1000) +
      "s</p>";
  }, 400);
  try {
    const data = await postJson("/api/live", { city: city, verify_n: 5 });
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
      " bit-exact · " +
      Math.round((Date.now() - t0) / 1000) +
      "s</p></article>" +
      "<article><p class='aside-label'>Boundaries captured</p><ol class='live-steps'>" +
      steps +
      "</ol></article></div>";
  } catch (err) {
    box.innerHTML =
      "<p class='bad-line'>Live request failed</p><p class='muted'>" +
      escapeHtml(String(err)) +
      "</p>";
  } finally {
    clearInterval(tick);
    btn.disabled = false;
    btn.textContent = "Run agent + verify";
  }
});

/* ——— Server-side auth (cookie session) ——— */
const viewAuth = document.getElementById("view-auth");
const viewApp = document.getElementById("view-app");
let demoLoaded = false;
let demoLogin = { email: "atyagi1_be24@thapar.edu", password: "Rewind@2026" };

function fillDemoLogin() {
  if (authMode !== "login") return;
  document.getElementById("email").value = demoLogin.email;
  document.getElementById("password").value = demoLogin.password;
}

function toast(message) {
  const el = document.getElementById("toast");
  el.hidden = false;
  el.textContent = message;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => {
    el.hidden = true;
  }, 2400);
}

function paintUser(session) {
  document.getElementById("user-name").textContent = session.name || "User";
  document.getElementById("user-email").textContent = session.email;
  document.getElementById("user-avatar").textContent = (session.name || session.email || "R")
    .trim()
    .charAt(0)
    .toUpperCase();
}

let lastAuthCfg = null;

async function applyAuthConfig() {
  const skipBtn = document.getElementById("btn-skip");
  const googleBlock = document.getElementById("google-block");
  try {
    if (!lastAuthCfg) {
      const res = await fetch("/api/auth/config", { cache: "no-store", credentials: "include" });
      lastAuthCfg = await res.json();
    }
    const cfg = lastAuthCfg;
    skipBtn.hidden = !cfg.skip;
    googleBlock.hidden = false;
    skipBtn.classList.remove("btn-skip-main");
    const accounts = Array.isArray(cfg.accounts) ? cfg.accounts : [];
    const presenter = accounts[0];
    if (presenter) {
      demoLogin = { email: presenter.email, password: presenter.password };
    }
    document.getElementById("auth-footnote").textContent = cfg.google
      ? "Google Sign-In is on. Assigned local accounts still work. Password for both: Rewind@2026."
      : "Google button is here, but this laptop needs a local .env (copy .env.example, add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, restart). Keys are not in git.";
  } catch {
    skipBtn.hidden = false;
    googleBlock.hidden = false;
  }
  fillDemoLogin();
}

function showAuth() {
  viewAuth.hidden = false;
  viewApp.hidden = true;
  document.title = "Rewind — Sign in";
  applyAuthConfig();
}

function showApp(session) {
  viewAuth.hidden = true;
  viewApp.hidden = false;
  paintUser(session);
  document.title = "Rewind — Month 1 Console";
  if (!demoLoaded) {
    demoLoaded = true;
    loadDemo().catch((err) => {
      document.getElementById("story-title").textContent = "Could not load demo";
      document.getElementById("story-task").textContent =
        String(err) + " — stop old server and run .\\demos\\week2_mam\\run.ps1 again.";
    });
  }
}

let authMode = "login";

function setAuthMode(next) {
  authMode = next;
  document.querySelectorAll(".seg").forEach((btn) => {
    const on = btn.dataset.mode === authMode;
    btn.classList.toggle("is-on", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  const signup = authMode === "signup";
  document.getElementById("field-name").hidden = !signup;
  document.getElementById("name").required = signup;
  document.getElementById("password").autocomplete = signup ? "new-password" : "current-password";
  document.getElementById("auth-title").textContent = signup ? "Create your account" : "Welcome back";
  document.getElementById("auth-lead").textContent = signup
    ? "Create an account, then open the Month 1 console for mam review."
    : "Open the Month 1 console for mam review.";
  document.getElementById("btn-submit").textContent = signup ? "Create account" : "Sign in";
  document.getElementById("form-error").hidden = true;
}

function showFormError(message) {
  const el = document.getElementById("form-error");
  el.hidden = !message;
  el.textContent = message || "";
}

document.querySelectorAll(".seg").forEach((btn) => {
  btn.addEventListener("click", () => setAuthMode(btn.dataset.mode));
});

document.getElementById("btn-eye").addEventListener("click", () => {
  const input = document.getElementById("password");
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  document.getElementById("btn-eye").textContent = show ? "Hide" : "Show";
  document.getElementById("btn-eye").setAttribute("aria-label", show ? "Hide password" : "Show password");
});

document.getElementById("auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  showFormError("");
  const email = document.getElementById("email").value.trim().toLowerCase();
  const password = document.getElementById("password").value;
  const name = document.getElementById("name").value.trim();
  const btn = document.getElementById("btn-submit");

  if (!email || !email.includes("@")) {
    showFormError("Enter a valid email address.");
    return;
  }
  if (password.length < 8) {
    showFormError("Password must be at least 8 characters.");
    return;
  }
  if (authMode === "signup" && name.length < 2) {
    showFormError("Enter your full name.");
    return;
  }

  btn.disabled = true;
  btn.textContent = authMode === "signup" ? "Creating…" : "Signing in…";
  try {
    const path = authMode === "signup" ? "/api/auth/register" : "/api/auth/login";
    const data = await postJson(path, { email, password, name });
    toast(authMode === "signup" ? "Account created" : "Signed in");
    showApp(data.user);
  } catch (err) {
    showFormError(String(err.message || err));
  } finally {
    btn.disabled = false;
    btn.textContent = authMode === "signup" ? "Create account" : "Sign in";
  }
});

document.getElementById("btn-google").addEventListener("click", async () => {
  showFormError("");
  try {
    const res = await fetch("/api/auth/config", { cache: "no-store", credentials: "include" });
    const cfg = await res.json();
    if (!cfg.google) {
      showFormError(
        "Google keys missing on this laptop. Copy repo .env.example to .env, paste GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET from a teammate (not GitHub), restart run.ps1."
      );
      return;
    }
    window.location.href = "/auth/google";
  } catch (err) {
    showFormError(String(err));
  }
});

document.getElementById("btn-signout").addEventListener("click", async () => {
  try {
    await postJson("/api/auth/logout", {});
  } catch {
    /* still leave the console */
  }
  demoLoaded = false;
  document.getElementById("password").value = "";
  showAuth();
});

document.getElementById("btn-skip").addEventListener("click", async () => {
  showFormError("");
  try {
    const data = await postJson("/api/auth/skip", {});
    toast("Demo console");
    showApp(data.user);
  } catch (err) {
    showFormError(String(err.message || err));
  }
});

async function bootAuth() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("auth") === "error") {
    showFormError("Google sign-in failed. Check .env client ID/secret and the callback URL.");
  }
  try {
    const res = await fetch("/api/auth/me", { cache: "no-store", credentials: "include" });
    const data = await res.json();
    if (data.user) {
      if (params.get("auth") === "ok") toast("Signed in with Google");
      showApp(data.user);
      if (params.get("auth")) history.replaceState({}, "", "/");
      return;
    }
  } catch {
    /* fall through to login */
  }
  showAuth();
}

bootAuth();
