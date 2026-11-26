"use strict";

const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="rewind-token"]').content;
const paths = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  disc: '<circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4z"/>',
  capture: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>',
  shield: '<path d="m12 2 8 3v6c0 5-4 9-8 11-4-2-8-6-8-11V5z"/><path d="m8 12 3 3 5-6"/>',
  compare: '<path d="M4 8h15m-4-4 4 4-4 4m5 4H5m4-4-4 4 4 4"/>',
  diamond: '<path d="m12 2 10 10-10 10L2 12z"/><circle cx="12" cy="12" r="3"/>',
  settings: '<path d="M12 3v3m0 12v3M3 12h3m12 0h3M6 6l2 2m8 8 2 2m0-12-2 2m-8 8-2 2"/><circle cx="12" cy="12" r="6"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1m0-14-1 1M6 18l-1 1"/>',
  moon: '<path d="M21 13a9 9 0 1 1-10-10 7 7 0 0 0 10 10Z"/>',
  "arrow-right": '<path d="M4 12h15m-6-6 6 6-6 6"/>',
  play: '<path d="m9 5 11 7-11 7z"/>',
  layers: '<path d="m12 3 10 5-10 5L2 8zm-9 9 9 5 9-5m-18 4 9 5 9-5"/>',
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 4 16 4 16 0V5M4 12v6c0 4 16 4 16 0v-6"/>',
  upload: '<path d="M12 16V3M7 8l5-5 5 5M4 15v6h16v-6"/>',
  download: '<path d="M12 3v13m-5-5 5 5 5-5M4 15v6h16v-6"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2 7m2-14v7h-7"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  code: '<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-2-15-4 18"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 4H4v12"/>',
  expand: '<path d="M8 4H4v4m12-4h4v4m0 8v4h-4m-8 0H4v-4"/>',
};
function putIcon(node, name) {
  node.setAttribute("aria-hidden", "true");
  // Icons are immutable local paths. API and recording values use text nodes.
  node.innerHTML = '<svg viewBox="0 0 24 24">' + paths[name] + '</svg>';
}
document.querySelectorAll("[data-icon]").forEach((node) => putIcon(node, node.dataset.icon));

function el(tag, value, className) {
  const node = document.createElement(tag);
  if (value !== undefined) node.textContent = value;
  if (className) node.className = className;
  return node;
}

function icon(name) {
  const node = el("i", undefined, "icon");
  putIcon(node, name);
  return node;
}

function button(label, handler, className = "btn") {
  const node = el("button", label, className);
  node.type = "button";
  node.onclick = handler;
  return node;
}

function badge(label, tone = "") {
  return el("span", label, "badge " + tone);
}

function blank(target, title, description) {
  const node = el("div", undefined, "empty");
  node.append(el("strong", title), document.createTextNode(description));
  target.replaceChildren(node);
}

function json(value, formatted = true) {
  return JSON.stringify(value ?? null, null, formatted ? 2 : 0);
}

function error(message) {
  $("alert-text").textContent = message instanceof Error ? message.message : message;
  $("alert").hidden = false;
}

function clearError() {
  $("alert").hidden = true;
}

let toastTimeout;
function notify(message) {
  $("notice").textContent = message;
  $("notice").hidden = false;
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => { $("notice").hidden = true; }, 3200);
}

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Rewind-Token": token},
    body: JSON.stringify(body),
  };
  const response = await fetch("/api/v1/" + path, options);
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error("The workspace returned an unreadable response.");
  }
  if (!response.ok) throw new Error(payload.error || "Workspace request failed.");
  return payload;
}

const pageNames = {
  overview: "Overview", recordings: "Recordings", capture: "Capture",
  verification: "Verification", compare: "Compare", providers: "Providers",
  settings: "Settings", welcome: "About Rewind",
};
const providerNames = {groq: "Groq", gemini: "Google Gemini", nvidia: "NVIDIA", xai: "xAI"};
const providerMarks = {groq: "g", gemini: "✦", nvidia: "N", xai: "𝕏"};
const systemTheme = matchMedia("(prefers-color-scheme: dark)");
let theme;
try { theme = localStorage.getItem("rewind-theme") || "dark"; } catch { theme = "dark"; }

function applyTheme(value) {
  theme = ["dark", "light", "system"].includes(value) ? value : "dark";
  const effective = theme === "system" ? (systemTheme.matches ? "dark" : "light") : theme;
  document.documentElement.dataset.theme = effective;
  $("theme").value = theme;
  $("theme-toggle").setAttribute("aria-label", effective === "dark" ? "Switch to light theme" : "Switch to dark theme");
  putIcon($("theme-toggle").firstElementChild, effective === "dark" ? "sun" : "moon");
  try { localStorage.setItem("rewind-theme", theme); } catch { /* Storage can be unavailable. */ }
}
function toggleTheme() {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
}
applyTheme(theme);
systemTheme.addEventListener("change", () => { if (theme === "system") applyTheme(theme); });
$("theme-toggle").onclick = toggleTheme;
$("theme").onchange = () => applyTheme($("theme").value);
$("dismiss").onclick = clearError;

let page = "overview";
let runs = [];
let jobs = [];
let providers = [];
let selectedId = null;
let selectedRun = null;
let step = 0;
let runTab = "timeline";
let evidenceTab = "request";
let treeVisible = false;
let recordingRequest = 0;
let filter = "all";
let listLimit = 60;
let playbackTimer;
let compareRequest = 0;
let alignment = [];
let comparisonSelection = -1;
let selectedVerification = null;
let busy = false;
const checkedProviders = new Map();

function go(target) {
  if (location.hash !== "#" + target) location.hash = target;
  else route();
}

function route() {
  const address = location.hash.slice(1);
  const previous = page;
  page = Object.hasOwn(pageNames, address) ? address : "overview";
  if (previous !== page) {
    window.scrollTo(0, 0);
    $("main").scrollTop = 0;
  }
  $("current-page").textContent = pageNames[page];
  document.querySelector(".skip").hidden = page === "welcome";
  if (page !== "recordings") stopPlayback();
  $("shell").hidden = page === "welcome";
  $("welcome").hidden = page !== "welcome";
  document.querySelectorAll(".screen").forEach((screen) => {
    screen.hidden = screen.id !== "page-" + page;
  });
  document.querySelectorAll("[data-page]").forEach((link) => {
    if (link.dataset.page === page) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  if (closeMenu() && page !== "welcome") $("main").focus({preventScroll: true});
  if (page === "recordings" && selectedId === null && runs.length) openRun(runs[0].id);
}
addEventListener("hashchange", route);
document.querySelector(".skip").onclick = (event) => {
  event.preventDefault();
  $("main").focus();
};
const mobileMenu = matchMedia("(max-width: 625px)");
const menuTrigger = $("menu-trigger");
const sidebar = $("workspace-sidebar");

function closeMenu({returnFocus = false} = {}) {
  const wasOpen = $("shell").classList.contains("menu-open");
  $("shell").classList.remove("menu-open");
  menuTrigger.setAttribute("aria-expanded", "false");
  if (wasOpen && returnFocus) menuTrigger.focus();
  return wasOpen;
}

menuTrigger.onclick = () => {
  if (closeMenu({returnFocus: true})) return;
  $("shell").classList.add("menu-open");
  menuTrigger.setAttribute("aria-expanded", "true");
  (sidebar.querySelector('[aria-current="page"]') || sidebar.querySelector("a"))?.focus();
};

sidebar.addEventListener("click", (event) => {
  if (event.target.closest("a")?.hash === location.hash && closeMenu()) {
    $("main").focus({preventScroll: true});
  }
});

mobileMenu.addEventListener("change", () => {
  if (!mobileMenu.matches) closeMenu();
});

document.addEventListener("keydown", (event) => {
  if (!$("shell").classList.contains("menu-open")) return;
  if (event.key === "Escape") {
    event.preventDefault();
    closeMenu({returnFocus: true});
  } else if (event.key === "Tab") {
    const links = [...sidebar.querySelectorAll("a[href]")].filter((link) => link.getClientRects().length);
    const index = links.indexOf(document.activeElement);
    if (index < 0 || (event.shiftKey ? index === 0 : index === links.length - 1)) {
      event.preventDefault();
      links[event.shiftKey ? links.length - 1 : 0]?.focus();
    }
  }
});


const runName = (run) => run.display_model || run.model || run.display_provider || run.provider || run.id;
const verificationText = (run) => (
  run.verification ? (run.verification.passed ? "Replay matched " + run.verification.replays + "×" : "Replay diverged") : "Not verified"
);
function dateLabel(value) {
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  return Number.isNaN(date.valueOf()) ? "" : date.toLocaleString(undefined, {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"});
}
function stepCount(count) { return count + (count === 1 ? " step" : " steps"); }
function sizeLabel(bytes) {
  if (!Number.isFinite(bytes)) return "—";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 ** 2) return (bytes / 1024).toFixed(1) + " KiB";
  if (bytes < 1024 ** 3) return (bytes / 1024 ** 2).toFixed(1) + " MiB";
  return (bytes / 1024 ** 3).toFixed(1) + " GiB";
}
function fillSelect(id, choices, emptyLabel) {
  const node = $(id);
  const old = node.value;
  node.replaceChildren(...(choices.length ? choices.map(({label, value}) => new Option(label, value)) : [new Option(emptyLabel, "")]));
  if (choices.some(({value}) => old === value)) node.value = old;
  return node.value !== old;
}

function drawOverview() {
  $("stat-runs").textContent = runs.length;
  $("stat-boundaries").textContent = runs.reduce((count, run) => count + run.n_boundaries, 0);
  const matched = runs.filter((run) => run.verification?.passed).length;
  const diverged = runs.filter((run) => run.verification && !run.verification.passed).length;
  $("stat-verified").textContent = matched;
  const recent = $("recent");
  recent.replaceChildren();
  if (!runs.length) {
    const firstRun = el("div", undefined, "first-run");
    const mark = el("span", undefined, "stat-icon");
    mark.append(icon("disc"));
    const copy = el("div");
    const action = el("a", "Capture your first run", "text-link");
    action.href = "#capture";
    copy.append(
      el("strong", "No recordings yet"),
      el("p", "Captured requests, responses, and replay results will appear here."),
      action,
    );
    firstRun.append(mark, copy);
    recent.append(firstRun);
  }
  if (runs.length) {
    const table = el("table", undefined, "recent-table");
    const header = table.createTHead().insertRow();
    for (const title of ["Script", "Outcome", "Steps", "Verification", "Recorded", ""]) {
      const heading = el("th", title);
      heading.scope = "col";
      header.append(heading);
    }
    const body = table.createTBody();
    for (const run of runs.slice(0, 5)) {
      const row = body.insertRow();
      const name = row.insertCell();
      name.append(el("strong", runName(run)), el("small", run.id));
      const script = run.provider === "script";
      const outcome = run.script_failed ? "Agent failed" : script ? "Completed" : "Recorded";
      row.insertCell().append(badge(outcome, run.script_failed ? "danger" : script ? "good" : ""));
      row.insertCell().textContent = run.n_boundaries;
      row.insertCell().append(badge(verificationText(run), run.verification?.passed ? "good" : run.verification ? "danger" : ""));
      row.insertCell().textContent = dateLabel(run.created_at);
      row.insertCell().append(button("Inspect", () => investigate(run.id), "btn recent-inspect"));
    }
    const scroll = el("div", undefined, "recent-scroll");
    scroll.append(table);
    recent.append(scroll);
  }
  const distribution = el("div", undefined, "distribution");
  for (const [label, count] of [["Matched", matched], ["Diverged", diverged], ["Not verified", runs.length - matched - diverged]]) {
    const line = el("div");
    const name = el("span", label);
    const dot = el("i", undefined, label === "Matched" ? "matched" : label === "Diverged" ? "diverged" : "unverified");
    name.prepend(dot);
    line.append(name, el("strong", count));
    distribution.append(line);
  }
  const replaySummary = el("div", undefined, "replay-summary");
  const ring = el("div", undefined, "replay-ring");
  ring.setAttribute("aria-hidden", "true");
  if (runs.length) {
    ring.style.setProperty("--matched", matched / runs.length * 100 + "%");
    ring.style.setProperty("--checked", (matched + diverged) / runs.length * 100 + "%");
  }
  ring.append(el("strong", runs.length), el("small", runs.length === 1 ? "recording" : "recordings"));
  replaySummary.append(ring, distribution);
  $("distribution").replaceChildren(replaySummary);
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const days = Array.from({length: 7}, (_, i) => {
    const from = new Date(now);
    from.setDate(from.getDate() - (6 - i));
    const until = new Date(from);
    until.setDate(until.getDate() + 1);
    return {from, count: runs.filter((run) => {
      const saved = new Date(run.created_at);
      return saved >= from && saved < until;
    }).length};
  });
  const max = Math.max(...days.map(({count}) => count));
  const chart = el("div", undefined, "chart-bars");
  for (const {from, count} of days) {
    const column = el("div", undefined, "chart-col");
    const meter = el("meter");
    meter.max = max || 1;
    meter.value = count;
    meter.setAttribute("aria-label", from.toLocaleDateString() + ": " + count + " recordings");
    column.append(el("span", count), meter, el("span", from.toLocaleDateString(undefined, {weekday: "short"})));
    chart.append(column);
  }
  $("chart").replaceChildren(chart);
}

function drawLibrary() {
  const query = $("filter-runs").value.trim().toLowerCase();
  const source = $("source-filter").value;
  const matches = runs.filter((run) => {
    if (filter === "failed" && !run.script_failed) return false;
    if (filter === "verified" && !run.verification?.passed) return false;
    if (source === "linked" && !run.has_source) return false;
    if (source === "unlinked" && run.has_source) return false;
    return [run.id, runName(run), run.provider, run.display_provider].some((value) => String(value || "").toLowerCase().includes(query));
  });
  $("library-count").textContent = matches.length;
  const target = $("run-list");
  target.replaceChildren();
  $("more-runs").hidden = matches.length <= listLimit;
  if (matches.length === 0) {
    blank(target, "No matching recordings", "Try a different filter, capture a script, or import a bundle.");
    return;
  }
  for (const run of matches.slice(0, listLimit)) {
    const item = button(undefined, () => openRun(run.id), "record");
    item.dataset.runId = run.id;
    item.title = run.id;
    item.setAttribute("aria-label", runName(run) + " · " + run.id);
    item.setAttribute("aria-pressed", String(run.id === selectedId));
    const tags = el("span", undefined, "record-badges");
    if (run.script_failed) tags.append(badge("Agent failed", "danger"));
    if (run.sample) tags.append(badge("Simulated", "warning"));
    if (run.counterfactual) tags.append(badge("Fork"));
    tags.append(badge(verificationText(run), run.verification?.passed ? "good" : ""));
    item.append(el("strong", runName(run)), el("small", run.id + " · " + stepCount(run.n_boundaries), "mono"), tags);
    target.append(item);
  }
}
function updateFilter() { listLimit = 60; drawLibrary(); }
$("filter-runs").oninput = updateFilter;
$("source-filter").onchange = updateFilter;
$("filters").onclick = (event) => {
  const item = event.target.closest("[data-filter]");
  if (!item) return;
  filter = item.dataset.filter;
  for (const option of $("filters").children) option.setAttribute("aria-pressed", String(option === item));
  updateFilter();
};
$("more-runs").onclick = () => { listLimit += 60; drawLibrary(); };
$("toggle-library").onclick = () => {
  const closed = $("investigation").classList.toggle("library-closed");
  $("library").hidden = closed;
  $("toggle-library").setAttribute("aria-expanded", String(!closed));
};

function enableResize(handle, panel, property, reverse) {
  const container = $("investigation");
  const grip = $(handle);
  const minimum = reverse ? 265 : 210;
  function maxWidth() {
    const otherPanel = $(reverse ? "library" : "inspector");
    return Math.max(minimum, Math.floor(container.clientWidth - (otherPanel.hidden ? 0 : otherPanel.offsetWidth + 13) - 313));
  }
  function resize(value) {
    const upper = maxWidth();
    const width = Math.max(minimum, Math.min(upper, value));
    container.style.setProperty(property, width + "px");
    grip.setAttribute("aria-valuemin", minimum);
    grip.setAttribute("aria-valuemax", upper);
    grip.setAttribute("aria-valuenow", width);
  }
  grip.onfocus = () => {
    grip.setAttribute("aria-valuemin", minimum);
    grip.setAttribute("aria-valuemax", maxWidth());
    grip.setAttribute("aria-valuenow", $(panel).offsetWidth);
  };
  grip.onkeydown = (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "Home") resize(minimum);
    else if (event.key === "End") resize(maxWidth());
    else resize($(panel).offsetWidth + (event.key === "ArrowLeft" ? -16 : 16) * (reverse ? -1 : 1));
  };
  grip.onpointerdown = (event) => {
    if (event.button !== 0) return;
    const start = event.clientX;
    const width = $(panel).offsetWidth;
    grip.setPointerCapture(event.pointerId);
    grip.onpointermove = (move) => resize(width + (move.clientX - start) * (reverse ? -1 : 1));
    grip.onlostpointercapture = () => { grip.onpointermove = null; };
  };
}
enableResize("library-resize", "library", "--library-width", false);
enableResize("evidence-resize", "inspector", "--evidence-width", true);

function drawSelectors() {
  const items = runs.map((run) => ({value: run.id, label: runName(run) + " · " + run.id}));
  const leftChanged = fillSelect("compare-left", items, "No recordings available");
  const rightChanged = fillSelect("compare-right", items, "No recordings available");
  if (rightChanged && items.length > 1 && $("compare-left").value === $("compare-right").value) $("compare-right").selectedIndex = 1;
  if (leftChanged || rightChanged) clearComparison();
  fillSelect("verify-run", items.filter((item, i) => runs[i].has_source), "No trusted recording available");
  syncForms();
}

let refreshRequest = 0;
async function refresh({quiet = false} = {}) {
  const request = ++refreshRequest;
  try {
    if (!quiet) clearError();
    const {jobs: jobData} = await api("jobs");
    const [library, scripts, readiness, coverage] = await Promise.all([
      api("runs" + ($("show-samples").checked ? "?samples=1" : "")),
      api("scripts"), api("providers"), api("coverage"),
    ]);
    if (request !== refreshRequest) return;
    jobs = jobData;
    runs = library.runs;
    providers = readiness.providers;
    if (fillSelect("script", scripts.scripts.map((script) => ({label: script, value: script})), "No Python scripts found")) $("trust").checked = false;
    $("workspace-path").textContent = scripts.root;
    $("settings-path").textContent = scripts.root;
    $("stat-storage").textContent = sizeLabel(coverage.storage_bytes);
    $("settings-storage").textContent = "SQLite file: " + sizeLabel(coverage.storage_bytes);
    $("provider-notice").textContent = readiness.notice;
    drawCoverage(coverage);
    drawProviders();
    drawOverview();
    drawLibrary();
    drawSelectors();
    drawJobs();
    if (selectedRun && page === "recordings") showRunTab(runTab);
    if (!selectedId && page === "recordings" && runs.length) await openRun(runs[0].id);
  } catch (problem) {
    if (request === refreshRequest) error(problem);
  } finally {
    if (request === refreshRequest) $("loading").hidden = true;
  }
}
$("refresh").onclick = () => refresh();
$("show-samples").onchange = () => refresh();

function investigate(id) {
  openRun(id);
  go("recordings");
}
async function openRun(id) {
  const request = ++recordingRequest;
  selectedId = id;
  selectedRun = null;
  step = 0;
  stopPlayback();
  clearError();
  for (const item of $("run-list").querySelectorAll("[data-run-id]")) item.setAttribute("aria-pressed", String(item.dataset.runId === id));
  $("export").disabled = true;
  $("boundary-count").textContent = "—";
  $("detail-title").textContent = "Loading recording…";
  $("detail-id").textContent = id;
  $("run-detail").replaceChildren();
  $("timeline").replaceChildren();
  $("timeline-start").hidden = true;
  $("timeline-end").hidden = true;
  $("evidence-body").hidden = true;
  $("no-evidence").hidden = false;
  $("step-badge").textContent = "—";
  $("playback").hidden = true;
  try {
    const {run} = await api("runs/" + encodeURIComponent(id));
    if (request !== recordingRequest) return;
    selectedRun = run;
    $("export").disabled = false;
    $("detail-title").textContent = run.metadata.product_model || run.model || run.provider || id;
    $("boundary-count").textContent = stepCount(run.boundaries.length);
    $("no-evidence").textContent = run.boundaries.length ? "Select a recorded step to inspect its evidence." : "No captured boundaries. See the recording summary for its outcome.";
    showRunTab("timeline");
    drawTimeline();
    if (run.boundaries.length) selectStep(0);
  } catch (problem) {
    if (request !== recordingRequest) return;
    $("detail-title").textContent = "Recording unavailable";
    error(problem);
  }
}
function showRunTab(tab) {
  runTab = tab;
  for (const item of $("run-tabs").children) item.setAttribute("aria-pressed", String(item.dataset.runTab === tab));
  $("timeline-panel").hidden = tab !== "timeline";
  const target = $("run-detail");
  target.replaceChildren();
  if (!selectedRun) return;
  const run = selectedRun;
  const summary = runs.find(({id}) => id === selectedId);
  if (tab === "timeline") {
    const tags = el("div", undefined, "actions");
    if (run.metadata.script_error) tags.append(badge("Agent failed", "danger"));
    if (run.metadata.counterfactual) tags.append(badge("What-if fork", "warning"));
    tags.append(badge("Integrity checked", "good"), badge(summary ? verificationText(summary) : "Not verified"));
    target.append(tags);
    if (run.metadata.script_error) target.append(el("p", run.metadata.script_error, "notice danger"));
    if (!run.boundaries.length) appendOutcome(target, run);
    return;
  }
  if (tab === "metadata") {
    const {product_source, ...metadata} = run.metadata;
    target.append(el("pre", json({id: selectedId, fingerprint: run.fingerprint, chain_algorithm: run.chain_algorithm, metadata})));
    return;
  }
  if (tab === "verification") {
    target.append(el("p", summary ? verificationText(summary) : "No stored verification"));
    if (run.metadata.product_source) target.append(button("Open verification", () => goVerify(selectedId)));
    else target.append(el("p", "Inspection only. No trusted workspace script is linked.", "notice"));
    return;
  }
  target.append(el("p", run.metadata.product_source ? "Trusted workspace script linked." : "Inspection only. No trusted workspace script is linked."));
  if (run.metadata.counterfactual) target.append(el("p", "Parent fingerprint: " + (run.metadata.parent_fingerprint || "Unavailable"), "mono path"));
  if (run.metadata.script_error) target.append(el("p", "Agent failed: " + run.metadata.script_error, "notice danger"));
  appendOutcome(target, run);
}
function appendOutcome(target, run) {
  if (!run.final_output) return;
  target.append(el("h3", "Captured output"), el("pre", run.final_output));
}
$("run-tabs").onclick = (event) => {
  const item = event.target.closest("[data-run-tab]");
  if (selectedRun && item) showRunTab(item.dataset.runTab);
};

function drawTimeline() {
  const target = $("timeline");
  target.replaceChildren();
  const boundaries = selectedRun?.boundaries || [];
  $("timeline-start").hidden = !boundaries.length;
  $("timeline-end").hidden = !boundaries.length;
  const failed = Boolean(selectedRun?.metadata.script_error);
  $("timeline-end").classList.toggle("failed", failed);
  $("timeline-end-text").textContent = failed ? "Execution ended with an error" : "End of recording";
  if (!boundaries.length) {
    blank(target, "No captured boundaries", "This recording can still have a terminal outcome.");
    return;
  }
  for (const [index, boundary] of boundaries.entries()) {
    const node = button(undefined, () => selectStep(index), "node");
    node.dataset.index = index;
    node.setAttribute("aria-pressed", "false");
    const symbol = el("span", undefined, "stat-icon");
    symbol.append(icon(boundary.kind === "tool" ? "settings" : boundary.kind === "http" ? "compare" : "code"));
    const label = el("span");
    label.append(el("small", "STEP " + index + " · " + boundary.kind.toUpperCase()), el("strong", boundary.key));
    node.append(symbol, label);
    target.append(node);
  }
  $("playback").hidden = false;
  $("scrub").max = String(boundaries.length - 1);
}
function selectStep(index, scroll = false) {
  const boundaries = selectedRun?.boundaries || [];
  if (!boundaries.length) return;
  const old = step;
  step = Math.min(boundaries.length - 1, Math.max(0, index));
  const target = $("timeline");
  target.children[old]?.setAttribute("aria-pressed", "false");
  const active = target.children[step];
  active?.setAttribute("aria-pressed", "true");
  if (scroll) active?.scrollIntoView({block: "nearest"});
  $("step-badge").textContent = "Step " + step;
  $("step-label").textContent = step + 1 + " / " + boundaries.length;
  $("scrub").value = String(step);
  $("scrub").setAttribute("aria-valuetext", "Step " + step);
  $("prev-step").disabled = step === 0;
  $("next-step").disabled = step >= boundaries.length - 1;
  $("play-step").disabled = boundaries.length <= 1;
  $("boundary-title").textContent = boundaries[step].key;
  $("boundary-kind").textContent = boundaries[step].kind;
  $("no-evidence").hidden = true;
  $("evidence-body").hidden = false;
  drawEvidence();
}
function stopPlayback() {
  clearInterval(playbackTimer);
  playbackTimer = undefined;
  $("play-step").textContent = "▶";
  $("play-step").setAttribute("aria-label", "Play stored steps");
}
function startPlayback() {
  const length = selectedRun?.boundaries.length || 0;
  if (length < 2) return;
  if (step === length - 1) selectStep(0, true);
  $("play-step").textContent = "Ⅱ";
  $("play-step").setAttribute("aria-label", "Pause stored steps");
  playbackTimer = setInterval(() => {
    if (step + 1 >= length) stopPlayback();
    else selectStep(step + 1, true);
  }, 660 / Number($("speed").value));
}
$("prev-step").onclick = () => selectStep(step - 1, true);
$("next-step").onclick = () => selectStep(step + 1, true);
$("scrub").oninput = () => selectStep(Number($("scrub").value), true);
$("play-step").onclick = () => playbackTimer ? stopPlayback() : startPlayback();
$("speed").onchange = () => { if (playbackTimer) { stopPlayback(); startPlayback(); } };

function evidenceValue() {
  const boundary = selectedRun.boundaries[step];
  const response = boundary.response;
  const stream = response && typeof response === "object" ? {
    chunks: response.chunks,
    chunk_bytes_b64: response.chunk_bytes_b64,
    chunk_offsets_ns: response.chunk_offsets_ns,
  } : {};
  if (evidenceTab === "chain") return boundary.chain_hash;
  if (evidenceTab === "stream" && !Object.values(stream).some((value) => value !== undefined)) return "No streamed chunks were recorded for this step.";
  return {request: boundary.request, response, stream, raw: boundary}[evidenceTab];
}
function evidenceText() {
  const value = evidenceValue();
  return evidenceTab === "chain" || (evidenceTab === "stream" && typeof value === "string") ? value : json(value, $("pretty").checked);
}
function treeNode(label, value, level = 0) {
  if (value === null || typeof value !== "object") {
    const preview = json(value, false);
    return el("div", label + ": " + preview.slice(0, 350) + (preview.length > 350 ? "…" : ""), "tree-value");
  }
  const node = el("details");
  const entries = Object.entries(value);
  node.append(el("summary", label + (Array.isArray(value) ? " [" + entries.length + "]" : " {" + entries.length + "}")));
  if (level === 0) node.open = true;
  const drawChildren = () => {
    if (node.children.length > 1) return;
    for (const [key, child] of entries.slice(0, 100)) node.append(treeNode(key, child, level + 1));
    if (entries.length > 100) node.append(el("div", "First 100 items shown. Use Copy for complete evidence.", "notice"));
  };
  if (node.open) drawChildren();
  node.addEventListener("toggle", () => { if (node.open) drawChildren(); });
  return node;
}
function drawCode(target, text, query) {
  target.classList.toggle("wrap", $("wrap").checked);
  const fragment = document.createDocumentFragment();
  const previewLimit = 60000;
  const lines = text.slice(0, previewLimit).split("\n");
  const needle = query.trim().toLowerCase();
  let matches = 0;
  for (const [index, line] of lines.slice(0, 1200).entries()) {
    const row = el("div", undefined, "code-line");
    const number = el("span", index + 1);
    number.setAttribute("aria-hidden", "true");
    const code = el("code");
    const searchLine = needle ? line.toLowerCase() : "";
    if (needle && searchLine.includes(needle)) {
      let at = 0;
      let match = searchLine.indexOf(needle);
      while (match !== -1 && matches < 500) {
        code.append(document.createTextNode(line.slice(at, match)), el("mark", line.slice(match, match + needle.length), "match"));
        at = match + needle.length;
        matches++;
        match = searchLine.indexOf(needle, at);
      }
      code.append(document.createTextNode(line.slice(at)));
    } else {
      const pieces = line.split(/("(?:[^"\\]|\\.)*"(?:\s*:)?|\b(?:true|false|null)\b|-?\b\d+(?:\.\d+)?\b)/g);
      for (const [position, piece] of pieces.entries()) {
        if (position % 2 === 0) code.append(document.createTextNode(piece));
        else code.append(el("span", piece, piece.startsWith('"') ? (piece.endsWith(":") ? "json-key" : "json-string") : "json-value"));
      }
    }
    row.append(number, code);
    fragment.append(row);
  }
  if (lines.length > 1200 || text.length > previewLimit) fragment.append(el("div", "Preview shortened. Copy or export for complete evidence.", "notice"));
  target.replaceChildren(fragment);
  return matches;
}
function drawEvidence() {
  const value = evidenceValue();
  const supportsTree = value !== null && typeof value === "object";
  const query = $("evidence-search").value;
  const useTree = treeVisible && supportsTree && !query.trim();
  $("evidence-tree-toggle").disabled = !supportsTree || Boolean(query.trim());
  $("evidence-tree-toggle").setAttribute("aria-expanded", String(useTree));
  $("evidence-tree").hidden = !useTree;
  $("evidence-code").hidden = useTree;
  if (useTree) {
    $("evidence-tree").replaceChildren(treeNode("Evidence", value));
    $("evidence-matches").textContent = "";
  } else {
    const matches = drawCode($("evidence-code"), evidenceText(), query);
    $("evidence-matches").textContent = query.trim() ? matches + (matches >= 500 ? "+ visible matches" : " visible matches") : "";
  }
}
$("evidence-tree-toggle").onclick = () => { treeVisible = !treeVisible; drawEvidence(); };
$("evidence-tabs").onclick = (event) => {
  const item = event.target.closest("[data-evidence]");
  if (!selectedRun || !item) return;
  evidenceTab = item.dataset.evidence;
  for (const tab of $("evidence-tabs").children) tab.setAttribute("aria-pressed", String(tab === item));
  drawEvidence();
};
$("evidence-search").oninput = drawEvidence;
$("wrap").onchange = drawEvidence;
$("pretty").onchange = drawEvidence;
$("copy-evidence").onclick = async () => {
  try {
    await navigator.clipboard.writeText(evidenceText());
    notify("Evidence copied.");
  } catch { error("Clipboard unavailable. Select and copy the evidence manually."); }
};
$("expand-evidence").onclick = () => {
  drawCode($("expanded-code"), evidenceText(), $("evidence-search").value);
  $("evidence-dialog").showModal();
};

$("import-trigger").onclick = () => $("import-file").click();
$("import-file").onchange = async ({target}) => {
  const file = target.files[0];
  if (!file) return;
  clearError();
  $("import-trigger").disabled = true;
  try {
    if (file.size > 32 * 1024 * 1024) throw new Error("The bundle exceeds the 32 MiB import limit.");
    const {run_id} = await api("import", {recording: JSON.parse(await file.text())});
    await refresh();
    await openRun(run_id);
    notify("Bundle imported for inspection.");
  } catch (problem) { error(problem); }
  finally { target.value = ""; $("import-trigger").disabled = false; }
};
$("export").onclick = async () => {
  const id = selectedId;
  $("export").disabled = true;
  clearError();
  try {
    const data = await api("export", {run_id: id});
    const link = el("a");
    link.href = URL.createObjectURL(new Blob([json(data)], {type: "application/json"}));
    link.download = "rewind-" + id + ".json";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 10000);
    notify("Bundle download requested.");
  } catch (problem) { error(problem); }
  finally { $("export").disabled = !selectedRun; }
};

function active(job) { return job && ["queued", "running"].includes(job.status); }
function syncForms() {
  const blocked = busy || jobs.some(active);
  $("capture").disabled = blocked || !$("script").value || !$("trust").checked;
  $("verify").disabled = blocked || !$("verify-run").value;
  $("compare").disabled = !$("compare-left").value || !$("compare-right").value;
}
async function submitJob(action, args) {
  clearError();
  busy = true;
  syncForms();
  try {
    const {job_id} = await api(action, args);
    if (action === "capture") $("trust").checked = false;
    else selectedVerification = job_id;
    await refresh();
  } catch (problem) { error(problem); }
  finally { busy = false; syncForms(); }
}
$("script").onchange = () => { $("trust").checked = false; syncForms(); };
$("trust").onchange = syncForms;
$("capture-form").onreset = () => setTimeout(syncForms, 0);
$("capture-form").onsubmit = (event) => {
  event.preventDefault();
  submitJob("capture", {source: $("script").value, trusted: $("trust").checked});
};
$("verify-form").onsubmit = (event) => {
  event.preventDefault();
  submitJob("verify", {run_id: $("verify-run").value, replays: Number($("replays").value)});
};
$("fewer").onclick = () => $("replays").stepDown();
$("more").onclick = () => $("replays").stepUp();
function goVerify(id) {
  $("verify-run").value = id;
  syncForms();
  go("verification");
}
async function cancelJob(job) {
  try {
    clearError();
    await api("cancel", {job_id: job.id});
    await refresh();
  } catch (problem) { error(problem); }
}
function jobHeadline(job) {
  if (active(job)) return job.type === "capture" ? "Recording in progress" : "Verification running";
  if (job.status === "cancelled") return "Cancelled";
  if (job.status === "failed") return "Job failed";
  if (job.type === "capture") return job.result?.script_error ? "Recording saved · agent failed" : "Recording saved";
  if (!job.result?.passed) return "Replay diverged";
  return runs.find((run) => run.id === job.recording_id)?.script_failed ? "Replay matched · original failure reproduced" : "Replay matched";
}
function drawCapture() {
  const job = jobs.find((entry) => entry.type === "capture");
  $("instrument").classList.toggle("active", Boolean(active(job)));
  drawClock();
  const root = $("capture-result");
  root.replaceChildren();
  if (!job) { blank(root, "Ready to capture", "Choose a script and confirm trust to start recording."); return; }
  drawJobResult(root, job);
}
function drawClock() {
  const job = jobs.find((entry) => entry.type === "capture");
  if (!active(job)) { $("capture-clock").textContent = job?.status || "Idle"; return; }
  const elapsed = Math.max(0, Math.floor(Date.now() / 1000 - job.created));
  $("capture-clock").textContent = String(Math.floor(elapsed / 60)).padStart(2, "0") + ":" + String(elapsed % 60).padStart(2, "0");
}
function drawJobResult(root, job) {
  const output = el("div", undefined, "job-result");
  const title = jobHeadline(job);
  const warning = job.result?.script_error || title.includes("failure reproduced");
  const tone = warning ? "warning" : job.status === "completed" ? (job.type === "verify" && !job.result?.passed ? "danger" : "good") : job.status === "failed" ? "danger" : "";
  output.append(el("h3", title, "notice " + tone));
  if (job.script) output.append(el("p", job.script, "mono path"));
  if (active(job)) {
    output.append(el("div", undefined, "indeterminate"), button("Cancel " + (job.type === "capture" ? "capture" : "verification"), () => cancelJob(job)));
  } else if (job.type === "capture" && job.result?.run_id) {
    const id = job.result.run_id;
    if (job.result.script_error) output.append(el("p", job.result.script_error, "notice danger"));
    output.append(el("p", job.result.boundaries + " captured boundaries · " + id));
    const actions = el("div", undefined, "actions");
    actions.append(button("Inspect recording", () => investigate(id), "btn primary"));
    if (runs.some((run) => run.id === id && run.has_source)) actions.append(button("Open verification", () => goVerify(id)));
    output.append(actions);
  } else if (job.type === "verify" && job.result) {
    const result = job.result;
    const metrics = el("div", undefined, "job-metrics");
    for (const [label, value] of [["Replays attempted", result.runs], ["Unique outputs", result.unique_outputs], ["Unique fingerprints", result.unique_fingerprints]]) {
      const metric = el("div");
      metric.append(el("small", label), el("strong", value ?? "—"));
      metrics.append(metric);
    }
    output.append(metrics, el("p", result.detail));
    if (job.recording_id) output.append(button("Inspect original recording", () => investigate(job.recording_id)));
  } else if (job.error) output.append(el("p", job.error));
  const details = el("details", undefined, "job");
  details.append(el("summary", "Raw job evidence"), el("pre", json(job)));
  output.append(details);
  root.append(output);
}
function drawJobs() {
  syncForms();
  drawCapture();
  const target = $("jobs");
  const result = $("verify-result");
  target.replaceChildren();
  result.replaceChildren();
  const selected = jobs.find((job) => job.id === selectedVerification) || jobs.find((job) => job.type === "verify");
  if (selected) drawJobResult(result, selected);
  else blank(result, "No verification result", "Select a trusted recording and start verification.");
  if (jobs.length === 0) blank(target, "No recent jobs", "Activity appears after a capture or verification starts.");
  for (const job of jobs.slice(0, 30)) {
    const row = el("div", undefined, "job");
    const line = el("div", undefined, "job-line");
    const label = el("div");
    label.append(el("strong", jobHeadline(job)), el("div", [job.script, dateLabel(job.created)].filter(Boolean).join(" · "), "muted"));
    line.append(label, badge(job.status));
    row.append(line);
    const actions = el("div", undefined, "actions");
    if (job.type === "verify") actions.append(button("View result", () => { selectedVerification = job.id; drawJobs(); }, "text-link btn"));
    if (active(job)) actions.append(button("Cancel " + (job.type === "capture" ? "capture" : "verification"), () => cancelJob(job)));
    if (actions.childElementCount) row.append(actions);
    if (job.type === "capture") {
      const details = el("details");
      details.append(el("summary", "Raw capture evidence"), el("pre", json(job)));
      row.append(details);
    }
    target.append(row);
  }
}
let polling = false;
setInterval(async () => {
  if (polling || document.hidden) return;
  polling = true;
  try {
    const {jobs: latest} = await api("jobs");
    const changed = latest.length !== jobs.length || latest.some((job, i) => job.id !== jobs[i]?.id || job.status !== jobs[i].status);
    if (changed) await refresh({quiet: true});
  } catch (problem) { error(problem); }
  finally { polling = false; }
}, 1500);
setInterval(drawClock, 1000);

let compareEvidence = "response";

function clearComparison() {
  compareRequest++;
  alignment = [];
  comparisonSelection = -1;
  $("compare-result").hidden = true;
  $("comparison").replaceChildren();
  $("compare-finding").replaceChildren();
  $("compare-alignment").replaceChildren();
  setCompareEvidenceVisible(false);
  $("compare-raw-left").replaceChildren();
  $("compare-raw-right").replaceChildren();
}
$("compare-left").onchange = clearComparison;
$("compare-right").onchange = clearComparison;
$("swap").onclick = () => {
  const left = $("compare-left").value;
  $("compare-left").value = $("compare-right").value;
  $("compare-right").value = left;
  clearComparison();
};
$("compare-form").onsubmit = async (event) => {
  event.preventDefault();
  clearComparison();
  clearError();
  const request = compareRequest;
  $("comparison").append(el("p", "Comparing recorded evidence…", "notice"));
  try {
    const {comparison} = await api("compare", {left: $("compare-left").value, right: $("compare-right").value});
    if (request === compareRequest) showComparison(comparison);
  } catch (problem) {
    if (request === compareRequest) { clearComparison(); error(problem); }
  }
};
function showComparison(report) {
  const primary = report.primary_difference;
  const first = report.first_difference;
  const code = primary?.category.replaceAll("-", " ");
  const summary = el("div", undefined, "notice " + (primary ? "warning" : "good"));
  summary.append(el("strong", primary ? code : "No divergence in the recorded evidence."));
  if (primary) summary.append(el("div", primary.summary));
  if (first && (first.a !== primary?.a || first.b !== primary?.b || first.label !== primary?.label)) {
    summary.append(el("div", "Earliest observed difference: baseline " + (first.a ?? "—") + " / candidate " + (first.b ?? "—") + " · " + first.label.replaceAll("-", " ")));
  }
  if (primary && report.interpretation) summary.append(el("small", report.interpretation));
  $("comparison").replaceChildren();
  $("compare-finding").replaceChildren(summary);
  alignment = report.alignment.slice();
  const outcome = report.outcome_difference || (primary?.a === null && primary?.b === null ? primary : null);
  if (outcome) alignment.push(outcome);
  $("compare-result").hidden = false;
  drawCompareLanes(alignment);
  for (const [index, row] of alignment.entries()) {
    const item = button(undefined, () => selectDifference(index), "alignment-row");
    const left = row.left?.key || (row.a === null ? (row.left ? "Final outcome" : "—") : "Step " + row.a);
    const right = row.right?.key || (row.b === null ? (row.right ? "Final outcome" : "—") : "Step " + row.b);
    item.append(el("span", row.a === null ? left : "#" + row.a + " · " + left), badge(row.label, row.label === "identical" ? "" : "warning"), el("span", row.b === null ? right : "#" + row.b + " · " + right));
    item.setAttribute("aria-pressed", "false");
    $("compare-alignment").append(item);
  }
  setCompareEvidenceVisible(alignment.length > 0);
  if (alignment.length) {
    const focus = primary ? alignment.findIndex((row) => row.a === primary.a && row.b === primary.b && row.label === primary.label) : 0;
    selectDifference(Math.max(0, focus));
  } else {
    blank($("compare-alignment"), "No captured steps to align", "Both recordings have no boundary evidence.");
    $("previous-diff").disabled = $("next-diff").disabled = true;
  }
}
function drawCompareLanes(rows) {
  const lanes = $("compare-lanes");
  const metrics = $("compare-metrics");
  lanes.replaceChildren();
  metrics.replaceChildren();
  const alignedSteps = Array.from(rows.entries()).filter(([, row]) => row.a !== null || row.b !== null);
  const steps = alignedSteps.map(([, row]) => row);
  lanes.hidden = !steps.length;
  for (const [label, side, indexKey] of [["Baseline", "left", "a"], ["Candidate", "right", "b"]]) {
    const lane = el("div", undefined, "compare-lane " + side);
    lane.append(el("strong", label));
    for (const [index, row] of alignedSteps) {
      const step = row[indexKey];
      const caption = step === null ? "Gap" : (row[side]?.key || "Step " + step);
      const point = button(undefined, () => selectDifference(index, true), "compare-point");
      point.dataset.alignmentIndex = index;
      point.setAttribute("aria-pressed", "false");
      point.classList.toggle("changed", row.label !== "identical");
      point.append(el("span", step === null ? "–" : step), el("small", caption));
      lane.append(point);
    }
    lanes.append(lane);
  }
  const changed = steps.filter((row) => row.a !== null && row.b !== null && row.label !== "identical").length;
  for (const [name, value] of [
    ["Baseline steps", steps.filter((row) => row.a !== null).length],
    ["Candidate steps", steps.filter((row) => row.b !== null).length],
    ["Changed steps", changed],
    ["Added in candidate", steps.filter((row) => row.a === null).length],
    ["Removed from candidate", steps.filter((row) => row.b === null).length],
  ]) {
    const metric = el("div", undefined, "comparison-metric");
    metric.append(el("span", name), el("strong", value));
    metrics.append(metric);
  }
}
function selectDifference(index, scroll = false) {
  const row = alignment[index];
  if (!row) return;
  const list = $("compare-alignment");
  list.children[comparisonSelection]?.setAttribute("aria-pressed", "false");
  comparisonSelection = index;
  list.children[index]?.setAttribute("aria-pressed", "true");
  for (const point of $("compare-lanes").querySelectorAll(".compare-point")) {
    point.setAttribute("aria-pressed", String(Number(point.dataset.alignmentIndex) === index));
  }
  if (scroll) list.children[index]?.scrollIntoView({block: "nearest"});
  drawCompareEvidence(row);
  $("previous-diff").disabled = !alignment.slice(0, index).some(({label}) => label !== "identical");
  $("next-diff").disabled = !alignment.slice(index + 1).some(({label}) => label !== "identical");
}
function setCompareEvidenceVisible(visible) {
  $("compare-evidence-controls").hidden = !visible;
  $("compare-evidence-panes").hidden = !visible;
}

function drawCompareEvidence(row) {
  $("compare-evidence-title").textContent = row.label.replaceAll("-", " ");
  const tabs = $("compare-evidence-tabs").querySelectorAll("button");
  for (const tab of tabs) {
    const mode = tab.dataset.compareEvidence;
    tab.disabled = mode !== "raw" && ![row.left, row.right].some((boundary) => boundary && Object.hasOwn(boundary, mode));
  }
  const preferred = Array.from(tabs).find((tab) => tab.dataset.compareEvidence === compareEvidence);
  const mode = preferred?.disabled ? "raw" : compareEvidence;
  for (const tab of tabs) tab.setAttribute("aria-pressed", String(tab.dataset.compareEvidence === mode));
  for (const side of ["left", "right"]) {
    const boundary = row[side];
    const value = mode === "raw" ? boundary : boundary?.[mode];
    $("compare-raw-" + side).textContent = value === undefined || !boundary ? "No corresponding evidence." : json(value);
  }
}

$("compare-evidence-tabs").onclick = (event) => {
  const mode = event.target.closest("button")?.dataset.compareEvidence;
  const row = alignment[comparisonSelection];
  if (!row || !mode) return;
  compareEvidence = mode;
  drawCompareEvidence(row);
};

$("previous-diff").onclick = () => selectDifference(alignment.findLastIndex((row, index) => index < comparisonSelection && row.label !== "identical"), true);
$("next-diff").onclick = () => selectDifference(alignment.findIndex((row, index) => index > comparisonSelection && row.label !== "identical"), true);

function drawProviders() {
  const target = $("providers");
  const overview = $("provider-overview");
  target.replaceChildren();
  overview.replaceChildren();
  for (const provider of providers) {
    const checked = checkedProviders.get(provider.name);
    const label = !provider.configured ? "Key not set" : checked?.ok ? "Catalogue reachable" : checked ? "Catalogue check failed" : "Key configured";
    const tone = checked?.ok ? "good" : !provider.configured || checked ? "warning" : "";
    const card = el("article", undefined, "panel provider-card");
    const head = el("div", undefined, "panel-head");
    head.append(el("span", providerMarks[provider.name] || "◇", "provider-mark"), el("h2", providerNames[provider.name] || provider.name));
    const body = el("div", undefined, "panel-body");
    body.append(el("span", provider.model, "mono"), el("p", checked?.message || "Catalogue check verifies account reachability."));
    const actions = el("div", undefined, "actions");
    const check = button("Check catalogue", async () => {
      clearError();
      check.disabled = true;
      check.textContent = "Checking…";
      try {
        checkedProviders.set(provider.name, await api("provider-check", {provider: provider.name}));
        drawProviders();
      } catch (problem) { error(problem); check.textContent = "Check catalogue"; check.disabled = false; }
    });
    check.disabled = !provider.configured;
    actions.append(badge(label, tone), check);
    body.append(actions);
    card.append(head, body);
    target.append(card);
    const row = el("div", undefined, "provider-row");
    row.append(el("span", providerMarks[provider.name] || "◇", "provider-mark"), el("strong", providerNames[provider.name] || provider.name), badge(label, tone));
    overview.append(row);
  }
}
function drawCoverage(data) {
  for (const id of ["coverage", "capture-coverage"]) {
    const target = $(id);
    target.replaceChildren();
    for (const [label, values] of [["Captured", data.supported], ["Coverage limits", data.limitations]]) {
      const box = el("div", undefined, "coverage-box");
      const list = el("ul");
      for (const value of values) list.append(el("li", value));
      box.append(el("h3", label), list);
      target.append(box);
    }
  }
}
$("audit-corpus").onclick = async () => {
  clearError();
  $("audit-corpus").disabled = true;
  $("audit-result").hidden = false;
  $("audit-result").textContent = "Auditing stored evidence…";
  try {
    const report = await api("corpus-audit", {});
    $("audit-result").textContent = [
      report.passed ? "PASS · No known-pattern matches" : "Review required",
      report.runs_scanned + " recordings · " + report.blobs_scanned + " blobs",
      report.integrity_failures + " integrity failures · " + report.runs_with_known_patterns + " recordings with possible secrets",
      report.unreadable_blobs + " unreadable blobs · " + report.blobs_with_invalid_stream_bytes + " invalid stream objects",
      report.scope,
    ].join("\n\n");
  } catch (problem) {
    $("audit-result").textContent = "Corpus audit did not complete.";
    error(problem);
  } finally { $("audit-corpus").disabled = false; }
};

const paletteInput = $("palette-search");
let paletteIndex = 0;
let commands = [];
let recentCommands = [];
try { recentCommands = JSON.parse(localStorage.getItem("rewind-recent-commands") || "[]"); } catch { /* Optional history. */ }
if (!Array.isArray(recentCommands)) recentCommands = [];
function openPalette() {
  $("palette").showModal();
  paletteInput.value = "";
  drawPalette();
  paletteInput.focus();
}
function drawPalette() {
  const query = paletteInput.value.trim().toLowerCase();
  const possibilities = [
    ...Object.entries(pageNames).map(([key, label]) => ({key, label, group: "Page", action: () => go(key)})),
    {key: "theme", label: "Toggle theme", group: "Action", action: toggleTheme},
    ...runs.map((run) => ({key: run.id, label: runName(run) + " · " + run.id, group: "Recording", action: () => investigate(run.id)})),
  ];
  commands = possibilities.filter((item) => (item.group + " " + item.label).toLowerCase().includes(query));
  if (!query) commands.sort((a, b) => {
    const rank = (item) => recentCommands.includes(item.key) ? recentCommands.indexOf(item.key) : recentCommands.length;
    return rank(a) - rank(b);
  });
  commands = commands.slice(0, 15);
  paletteIndex = 0;
  const target = $("palette-results");
  target.replaceChildren();
  if (!commands.length) { blank(target, "No commands found", "Try a page name, script, or recording ID."); return; }
  for (const [index, item] of commands.entries()) {
    const row = button(undefined, () => runCommand(index), "palette-item");
    row.append(el("small", !query && recentCommands.includes(item.key) ? "Recent" : item.group));
    const position = query ? item.label.toLowerCase().indexOf(query) : -1;
    if (position >= 0) row.append(
      document.createTextNode(item.label.slice(0, position)), el("mark", item.label.slice(position, position + query.length)),
      document.createTextNode(item.label.slice(position + query.length)),
    );
    else row.append(document.createTextNode(item.label));
    target.append(row);
  }
  highlightPalette(0);
}
function highlightPalette(index) {
  if (!commands.length) return;
  paletteIndex = (commands.length + index) % commands.length;
  for (const [position, item] of [...$("palette-results").children].entries()) item.classList.toggle("current", position === paletteIndex);
  $("palette-results").children[paletteIndex]?.scrollIntoView({block: "nearest"});
}
function runCommand(index) {
  const item = commands[index];
  if (!item) return;
  recentCommands = [item.key, ...recentCommands.filter((key) => key !== item.key)].slice(0, 5);
  try { localStorage.setItem("rewind-recent-commands", JSON.stringify(recentCommands)); } catch { /* Optional history. */ }
  $("palette").close();
  item.action();
}
$("search-trigger").onclick = openPalette;
paletteInput.oninput = drawPalette;
$("palette").addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    paletteInput.focus();
    highlightPalette(paletteIndex + (event.key === "ArrowDown" ? 1 : -1));
  } else if (event.key === "Enter" && event.target === paletteInput) {
    event.preventDefault();
    runCommand(paletteIndex);
  }
});
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k" && !$("evidence-dialog").open) {
    event.preventDefault();
    if ($("palette").open) $("palette").close();
    else {
      closeMenu();
      openPalette();
    }
  }
});
document.querySelectorAll("[data-close]").forEach((node) => {
  node.onclick = () => $(node.dataset.close).close();
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh({quiet: true});
});

route();
refresh();

function drawSignalArt(canvas) {
  const {width, height} = canvas.getBoundingClientRect();
  if (!width || !height) return;
  const scale = Math.min(devicePixelRatio || 1, 2);
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const context = canvas.getContext("2d");
  if (!context) return;
  context.scale(scale, scale);

  const gradient = context.createLinearGradient(0, 0, width, 0);
  gradient.addColorStop(0, "#434aea00");
  gradient.addColorStop(0.27, "#6395ff");
  gradient.addColorStop(0.65, "#ab75ff");
  gradient.addColorStop(1, "#8457fa00");

  for (let line = 0; line < 6; line++) {
    context.beginPath();
    context.globalAlpha = line === 0 ? 0.98 : 0.28 - line * 0.026;
    context.strokeStyle = gradient;
    context.lineWidth = line === 0 ? 2 : 1;
    context.shadowColor = "#9065ff";
    context.shadowBlur = line === 0 ? 15 : 0;
    for (let step = 0; step <= 120; step++) {
      const part = step / 120;
      const envelope = Math.sin(Math.PI * part);
      const ripple = Math.sin(part * 18 + line * 0.16) * envelope * height * 0.12;
      const y = height * (0.68 - part * 0.23) + ripple + line * 5 * envelope;
      if (step === 0) context.moveTo(0, y);
      else context.lineTo(part * width, y);
    }
    context.stroke();
  }
}

const artwork = new ResizeObserver((entries) => {
  for (const {target} of entries) drawSignalArt(target);
});
document.querySelectorAll(".signal-art").forEach((canvas) => artwork.observe(canvas));
