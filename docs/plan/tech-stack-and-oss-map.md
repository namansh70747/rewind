# Tech Stack & OSS Map

This is Rewind's **build-vs-buy technology map**: for every hard part of a flight recorder & time-travel debugger for AI agents, it names the chosen free/OSS library, its license, the specific difficulty it solves, and the trap to watch for. It exists so the team never re-litigates a dependency mid-sprint — every pick here is deliberate, pinned, and honest about maturity.

> Package: `flightrecorder` · CLI: `fr` · Repo: `github.com/namansh70747/rewind`
>
> **The core law (repeated everywhere in this repo):** *replay* = **playback** — serve recorded bytes, bit-exact, zero API calls. *fork* = **best-effort re-execution** for exploration, and is **never** advertised as faithful.

Related planning docs: [README](./README.md) · [Roadmap (6 months)](./roadmap-6-months.md) · [Milestones & exit criteria](./milestones-and-exit-criteria.md) · [Risks & spikes](./risks-and-spikes.md) · [Algorithms & math](./algorithms-and-math.md) · [Competitive landscape](./competitive-landscape.md) · [Team & cadence](./team-and-cadence.md)

---

## 1. The one architectural call that drives everything

**We capture at the `httpx` transport layer — not at the instrumentation layer.**

Both the OpenAI and Anthropic Python SDKs ride on `httpx`. A single custom transport therefore sits underneath *both* SDKs and sees the one thing bit-exact replay requires: **raw bytes** — request/response headers, body, and the exact SSE (server-sent events) chunk boundaries and their timing.

The instrumentation ecosystem (OpenInference, OpenLLMetry, the official `opentelemetry-instrumentation-*` libs) does something fundamentally different. It emits **OpenTelemetry spans** with prompt/response content attached as *attributes* — opt-in, often truncated, semantically normalized. That is the **presentation / semantic layer**. It is enough to *render* a run for a human; it is **not** enough to *replay* one byte-for-byte, because it discards headers, SSE framing, and timing.

| Layer | What it sees | Good for | Our use |
|---|---|---|---|
| `httpx` transport (**ours**) | raw bytes, headers, SSE chunks + timing | **bit-exact replay** | capture + replay **core** |
| OTel / OpenInference / OpenLLMetry | normalized span attributes (truncated content) | rendering, search, dashboards | **semantic / UX layer only** |

**Decision:** Lock the transport-capture point in **Phase 0**. Everything downstream — storage, scrubbing, TUI, analytics — reads from the bytes the transport records. OTel is normalized *in* at ingest for presentation, and never becomes our on-disk format (see [§5](#5-opentelemetry-genai-semantic-conventions--current-state)).

---

## 2. Subsystem-by-subsystem map

Each subsystem below has a decision table row plus a short **the difficulty → the reference solution** note.

### 2.1 Interception (monkeypatch primitive & semantic instrumentation)

| Subsystem | Pick | Runner-up | License | Why | Gotcha | Pinned |
|---|---|---|---|---|---|---|
| Interception | **OpenInference** (semantic layer) on **`wrapt`** (mechanism) | OpenLLMetry | Apache-2.0 / BSD-2 | Best agent/tool/MCP coverage incl. MCP instrumentor + Claude Agent SDK; `wrapt` is the patch primitive every LLM lib uses | Instrumenting with **both** OpenInference **and** OpenLLMetry = duplicate spans — pick one | `wrapt>=1.17` |

**The difficulty → the reference solution.** The difficulty is safely wrapping SDK call sites without breaking their signatures or async behavior. `wrapt` (BSD-2, [github.com/GrahamDumpleton/wrapt](https://github.com/GrahamDumpleton/wrapt)) is the canonical `wrap_function_wrapper` primitive underneath every LLM instrumentation library, so we build on it directly. For the *semantic* layer we reuse **OpenInference** (Arize, Apache-2.0, [github.com/Arize-ai/openinference](https://github.com/Arize-ai/openinference), ~1.1k stars) for its agent/tool/MCP coverage; **OpenLLMetry** (Traceloop, Apache-2.0, [github.com/traceloop/openllmetry](https://github.com/traceloop/openllmetry), ~7.4k stars) is the runner-up for its broad auto-instrument and close tracking of OTel semconv. The official `opentelemetry-instrumentation-*` libs (Apache-2.0) are the canonical emitter. All of these can capture content (`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`) — enough to *render*, not to *replay*.

### 2.2 HTTP record–replay core

| Subsystem | Pick | Runner-up | License | Why | Gotcha | Pinned |
|---|---|---|---|---|---|---|
| HTTP record–replay | **Custom `httpx` transport** (`BaseTransport` / `AsyncBaseTransport`) | `vcrpy` (non-streaming smoke tests only) | (our code) / MIT | One hook covers OpenAI + Anthropic; full control of SSE chunk bytes + timing; ~200 lines | **Scrub `Authorization` / `api-key` before committing cassettes**; pick matching keys carefully | `httpx` per SDK constraint; `respx>=0.21` (dev); optional `vcrpy==8.3.0` |

**The difficulty → the reference solution.** The difficulty is recording and replaying **streaming** LLM responses (SSE) bit-exact. The obvious buy — `vcrpy` (MIT, [pypi.org/project/vcrpy/](https://pypi.org/project/vcrpy/), v8.3.0) — is the classic cassette recorder, but its `httpx` + async + streaming path has been historically buggy ([vcrpy#597](https://github.com/kevin1024/vcrpy/issues/597)), which is a dealbreaker for LLM SSE. `respx` (BSD-3, [github.com/lundberg/respx](https://github.com/lundberg/respx)) is a *mocker* for the replay/test side, not a recorder. So we **build** a thin custom transport as the capture+replay core: one hook under both SDKs, full control of SSE chunks and inter-chunk timing, ~200 lines. `vcrpy` stays as a runner-up for non-streaming smoke tests. **Matching keys:** method + URL + body-hash, ignoring volatile headers (`x-request-id`, `date`). **Secrets:** scrub auth headers before any cassette is committed.

### 2.3 Determinism shims (time, RNG, UUID, hash order)

| Subsystem | Pick | Runner-up | License | Why | Gotcha | Pinned |
|---|---|---|---|---|---|---|
| Determinism | **`time-machine`** | `freezegun` | MIT / Apache-2.0 | Mocks time at the C layer — ~100–200x faster than freezegun's per-module attribute scanning | UUID/hash order need special handling (below) | `time-machine>=3.2` |

**The difficulty → the reference solution.** The difficulty is that an agent's output depends on hidden nondeterministic inputs beyond the network: wall-clock time, RNG, UUIDs, and hash ordering. For **time**, `time-machine` (MIT, [pypi.org/project/time-machine/](https://pypi.org/project/time-machine/)) beats `freezegun` (Apache-2.0) by mocking at the C layer — [~100–200x faster](https://adamj.eu/tech/2021/02/19/freezegun-versus-time-machine/). For **RNG**, seed `random.seed()` and `numpy` `default_rng(seed)`, and **record the seeds in the cassette**. For **UUIDs**, seeding does *not* help — `uuid4` pulls from `os.urandom` — so we **record and replay each generated UUID** (patch `uuid.uuid4`). For **hash order**, `PYTHONHASHSEED` must be set *before* interpreter start, so replay must relaunch/spawn a subprocess.

### 2.4 Storage (hot write path)

| Subsystem | Pick | Runner-up | License | Why | Gotcha | Pinned |
|---|---|---|---|---|---|---|
| Run/index store | **SQLite (WAL mode)** | — | Public domain (stdlib) | Concurrent reader + single writer; zero-dependency; the record index | WAL semantics: one writer at a time | stdlib |
| Payload compression | **`zstandard`** | — | BSD-3 | Compress payload blobs; excellent ratio/speed | **Record level + dict** for reproducible decompress | `zstandard>=0.23` |
| Content addressing | **`blake3`** | `hashlib.blake2b` (stdlib) | CC0 / Apache-2.0 | Content-addressing/dedup; faster than sha256, parallel/streaming | Keep stdlib `blake2b` as fallback | `blake3>=1.0` |

**The difficulty → the reference solution.** The difficulty is a durable, concurrent, dedup-friendly store on the **hot write path** without a server. **SQLite in WAL mode** (public domain, stdlib) is the primary run/index store — concurrent reader with a single writer, no external process. Payload blobs are compressed with **`zstandard`** (BSD-3, [github.com/indygreg/python-zstandard](https://github.com/indygreg/python-zstandard), v0.25); we **record the compression level and dictionary** so decompression is reproducible. Content addressing / dedup uses **`blake3`** (CC0/Apache-2.0, [github.com/oconnor663/blake3-py](https://github.com/oconnor663/blake3-py)) — faster than sha256, parallel and streaming — with stdlib `hashlib.blake2b` as a fallback.

### 2.5 Analytics store (Phase 2, cold path)

| Subsystem | Pick | Runner-up | License | Why | Gotcha | Pinned |
|---|---|---|---|---|---|---|
| Analytics/columnar | **DuckDB + PyArrow/Parquet** | — | MIT / Apache-2.0 | Fast columnar analytics over many runs for clustering | **Not** the hot-write path — Phase 2 only | `duckdb>=1.3`, `pyarrow>=17` |

**The difficulty → the reference solution.** The difficulty is analytical queries across thousands of runs (for failure clustering). **DuckDB** (MIT) over **PyArrow/Parquet** (Apache-2.0) is the embedded columnar engine — but strictly for **analytics**, never the hot write path, and only in Phase 2.

### 2.6 Vector store (embedded, Phase 2)

| Subsystem | Pick | Runner-up | License | Why | Gotcha | Pinned |
|---|---|---|---|---|---|---|
| Embedded vectors | **LanceDB** | `sqlite-vec` | Apache-2.0 / (Apache/MIT) | Truly embedded, disk-scale ANN, Arrow-native | `sqlite-vec` is pre-v1 **brute-force only** | LanceDB (Phase 2) |

**The difficulty → the reference solution.** The difficulty is similarity search over run embeddings **without a server**. **LanceDB** (Apache-2.0, [github.com/lancedb/lancedb](https://github.com/lancedb/lancedb), ~11k stars) is the pick — truly embedded, disk-scale ANN, Arrow-native. **`sqlite-vec`** (Apache/MIT, [github.com/asg017/sqlite-vec](https://github.com/asg017/sqlite-vec)) rides our existing SQLite and is a good Phase-1 option at **<1M vectors**, but it is pre-v1 and brute-force only ([sqlite-vec#25](https://github.com/asg017/sqlite-vec/issues/25)) — runner-up. Chroma (Apache-2.0) is embedded but memory-loaded; Qdrant local mode is dev/test only. **No SSPL/AGPL traps here** — avoid Redis/RediSearch (SSPL).

### 2.7 CLI / TUI & waterfall visualization

| Subsystem | Pick | Runner-up | License | Why | Gotcha | Pinned |
|---|---|---|---|---|---|---|
| CLI | **Typer** (vendors Click) | Click | MIT | Type-hint driven, ergonomic | — | `typer>=0.12` |
| Terminal render | **Rich** | — | MIT | Tables/trees for `fr` output | — | `rich>=13` |
| Scrubber TUI | **Textual** | — | MIT | Interactive time-travel scrubber ([textual.textualize.io](https://textual.textualize.io)) | Moves fast — **pin a known-good minor** | `textual~=1.0` |
| Waterfall (v1) | **Reuse Perfetto UI** | Jaeger UI | Apache-2.0 | Zero-build, client-side trace load, SQL over spans ([ui.perfetto.dev](https://ui.perfetto.dev)) | Jaeger UI needs a backend (violates zero-server) | — |
| Web timeline (deferred) | **FastAPI + React** | — | MIT | Only **after** E2E works | Deferred | `fastapi>=0.115` |

**The difficulty → the reference solution.** The difficulty is a good developer UX for scrubbing and a **span waterfall** without building a frontend. CLI/TUI is settled: **Typer** (MIT, vendors Click) over Click, **Rich** (MIT) for tables/trees, **Textual** (MIT) for the interactive scrubber (pin a known-good minor — it moves fast). For the **waterfall**, the strong recommendation is to **reuse Perfetto UI** (Apache-2.0, [ui.perfetto.dev](https://ui.perfetto.dev)) as the zero-build v1 viewer — it loads a trace file entirely client-side and gives SQL over spans for free. Because we can also **OTLP-export**, power users can open runs in Jaeger/Tempo/Phoenix at no cost. Jaeger UI is a runner-up but needs a backend, violating our zero-server principle. A bespoke **FastAPI + React** web timeline is deferred until E2E works.

### 2.8 ML — clustering, embeddings, fine-tuning (Phase 2, non-blocking)

| Subsystem | Pick | Runner-up | License | Why | Gotcha | Pinned |
|---|---|---|---|---|---|---|
| Clustering | **`sklearn.cluster.HDBSCAN`** | standalone `hdbscan` | BSD-3 | HDBSCAN now **built into scikit-learn** — no extra compiled dep | Use standalone `hdbscan` only for `approximate_predict` | `scikit-learn>=1.5` (v1.8) |
| Embeddings | **`sentence-transformers`** + **bge-small-en-v1.5** | `model2vec` | Apache-2.0 (model MIT) | Beats all-MiniLM on MTEB; tiny/CPU-friendly | — | `sentence-transformers>=3.0` |
| Dim-reduction (viz) | **`umap-learn`** | — | BSD-3 | Visualization only | Not for clustering itself | `umap-learn>=0.5.6` |
| Weak supervision | *(hand-written labeling functions)* | `snorkel` | (Apache-2.0) | Avoid a hard dep on abandonware | `snorkel` **effectively unmaintained** (last release Feb 2024) | — |
| LoRA/QLoRA (stretch) | `peft` + `trl` | `unsloth` | Apache-2.0 | Deferred **Phase-2 stretch / cut-line** | `unsloth` multi-GPU is commercially gated | deferred |
| Local LLM | `ollama` | — | MIT (tool) | Optional | **Model weights are NOT MIT** — Llama/Gemma restricted, non-OSI | deferred |

**The difficulty → the reference solution.** The difficulty is grouping failing runs into meaningful clusters cheaply, on CPU. **Staff call:** ship **`sentence-transformers`** (Apache-2.0) with **bge-small-en-v1.5** (model MIT — beats all-MiniLM on MTEB, tiny/CPU) → **`sklearn.cluster.HDBSCAN`** (BSD-3, v1.8; built-in avoids an extra compiled dependency) → optional **`umap-learn`** (BSD-3) for viz. `model2vec` (MIT) is a runner-up embedder (static, ~50x smaller, no torch at inference). **Defer** `snorkel`, `peft`, `unsloth`, and `trl`. Prefer hand-written labeling functions over a hard `snorkel` dependency. All ML is **Phase 2, non-blocking** — it must never block E2E, and **LoRA is an explicit Phase-2 stretch / cut-line**.

### 2.9 Testing libraries

| Subsystem | Pick | Runner-up | License | Why | Gotcha | Pinned |
|---|---|---|---|---|---|---|
| Snapshot testing | **`syrupy`** | — | Apache-2.0 | Non-deterministic-field matchers — assert `replay-output == recorded-output` | — | `syrupy>=4.6` |
| Property testing | **`hypothesis`** | — | MPL-2.0 (weak copyleft) | Round-trip / idempotency tests | **MPL-2.0 — test-only; log it** in license audit | `hypothesis>=6.100` |
| Replay-transport driver | **`pytest-httpx` / `respx`** | — | BSD-3 | Drive the replay transport in tests | — | `pytest-httpx>=0.30` |

**The difficulty → the reference solution.** The difficulty is *proving* that replay is bit-exact and round-trips are lossless. **`syrupy`** (Apache-2.0, [pypi.org/project/syrupy/](https://pypi.org/project/syrupy/)) is a snapshot plugin with non-deterministic-field matchers — perfect for asserting `replay-output == recorded-output`. **`hypothesis`** (MPL-2.0, weak copyleft, **test-only — log it**) drives round-trip/idempotency property tests. **`pytest-httpx`/`respx`** (BSD-3) drive the replay transport in tests.

---

## 3. Recommended pinned stack

```toml
# --- Core capture & replay -------------------------------------------------
wrapt>=1.17                 # BSD-2   patch primitive (mechanism)
openinference-instrumentation  # Apache-2.0  semantic layer (pick; NOT for replay)
httpx                       # per SDK constraint  custom BaseTransport = replay core
# (custom flightrecorder transport: ~200 lines, our code)
time-machine>=3.2           # MIT     deterministic time (C-layer, ~100-200x vs freezegun)

# --- Storage ---------------------------------------------------------------
# sqlite (stdlib, WAL)      # public domain  run/index store (hot path)
zstandard>=0.23             # BSD-3   payload compression (record level+dict)
blake3>=1.0                 # CC0/Apache-2.0  content-addressing/dedup

# --- Semantic / UX ---------------------------------------------------------
typer>=0.12                 # MIT     CLI (vendors Click)
rich>=13                    # MIT     tables/trees
textual~=1.0                # MIT     interactive scrubber TUI (pin known-good minor)
# Perfetto UI (Apache-2.0)  # reuse ui.perfetto.dev as zero-build waterfall (v1)

# --- Analytics + ML (Phase 2) ---------------------------------------------
duckdb>=1.3                 # MIT     analytics (cold path only)
pyarrow>=17                 # Apache-2.0  Parquet columnar
# lancedb                   # Apache-2.0  embedded vector store (runner-up: sqlite-vec)
scikit-learn>=1.5           # BSD-3   sklearn.cluster.HDBSCAN (built-in)
sentence-transformers>=3.0  # Apache-2.0  embeddings (bge-small-en-v1.5, model MIT)
umap-learn>=0.5.6           # BSD-3   viz only

# --- Testing ---------------------------------------------------------------
syrupy>=4.6                 # Apache-2.0  snapshot: replay==recorded
hypothesis>=6.100           # MPL-2.0  property tests (TEST-ONLY, weak copyleft)
pytest-httpx>=0.30          # BSD-3   drive replay transport
respx>=0.21                 # BSD-3   mocker (dev/test side)

# --- Deferred (do NOT add until justified) ---------------------------------
# fastapi>=0.115            # MIT     web timeline (after E2E)
# vcrpy==8.3.0              # MIT     non-streaming smoke tests only
# peft / trl               # Apache-2.0  LoRA/QLoRA — Phase-2 stretch / cut-line
# unsloth                  # Apache-2.0 core; multi-GPU commercially gated
# ollama                   # MIT tool; MODEL WEIGHTS non-OSI (Llama/Gemma)
# snorkel                  # Apache-2.0 but effectively unmaintained (Feb 2024)
# sqlite-vec               # Apache/MIT; pre-v1, brute-force only
```

---

## 4. Licensing & maturity honesty check

The **core stack is all permissive** — MIT / BSD / Apache-2.0 / public-domain / CC0 — with **no copyleft in shipped runtime code**. The items below are the ones to flag, watch, or keep out of the runtime dependency graph.

| Dependency | Flag | Detail | Mitigation |
|---|---|---|---|
| `hypothesis` | **Weak copyleft (MPL-2.0)** | Fine, but **not permissive** | **Test-only** — log in license audit, never a runtime dep |
| `ollama` (models) | **Non-OSI model weights** | Tool is MIT, but **Llama/Gemma weights are restricted**, not OSI | Deferred; treat weights license separately from the tool |
| `unsloth` | **Commercially gated** | Apache-2.0 single-GPU core; **multi-GPU gated** | Deferred stretch only |
| `snorkel` | **Abandonware risk** | Apache-2.0 but **last release Feb 2024** | Prefer hand-written labeling functions; **no hard dependency** |
| `sqlite-vec` | **Pre-v1, immature** | **Brute-force only**, no ANN index yet ([#25](https://github.com/asg017/sqlite-vec/issues/25)) | Runner-up only, <1M vectors; LanceDB is the real pick |
| OTel GenAI semconv | **Unstable / unversioned** | **Biggest stability risk to the "vendor-neutral" thesis** (see §5) | Own internal schema; normalize OTel at ingest edges |

**Explicitly avoided license traps:** Redis / RediSearch (**SSPL**) and any AGPL vector store — none are in the map.

---

## 5. OpenTelemetry GenAI semantic conventions — current state

**As of mid-2026, nothing in the GenAI conventions is Stable.** Every GenAI span and attribute is marked **'Development'**. In **June 2026** the work split into a dedicated repo, **[open-telemetry/semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai)**, with **no versioned releases** and a **TODO schema URL**. This is why OTel is our **presentation layer only** and never our on-disk format.

**Operation names** (`gen_ai.operation.name`) currently span: `chat`, `generate_content`, `embeddings`, `execute_tool`, `create_agent`, `invoke_agent`.

**Attribute churn we must handle across both generations at ingest:**

| Change | Old → New | Since |
|---|---|---|
| Provider identifier | `gen_ai.system` → `gen_ai.provider.name` | — |
| Token usage | `prompt_tokens`/`completion_tokens` → `gen_ai.usage.input_tokens`/`output_tokens` | v1.27 |
| Message content | per-message **events** → span attributes `gen_ai.input.messages` / `gen_ai.output.messages` / `gen_ai.system_instructions` | v1.37 |
| Evaluation | new `gen_ai.evaluation.result` event | v1.38 |
| MCP | material moved into the new dedicated repo | 2026 |

**Content capture** is **opt-in / off by default** (`OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`). Frameworks in the wild **emit multiple generations simultaneously**, so we must **normalize at ingest** and publish a **"tested-with" matrix**.

**Implication (the rule):** build our **own internal recording schema**, **normalize OTel at the edges**, and **never couple the on-disk format to the unstable spec**. OTel field names must never become our storage format.

**Sources:**
- [github.com/open-telemetry/semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai)
- [opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/)
- [john-hodge.com/blog/opentelemetry-genai-semantic-conventions/](https://john-hodge.com/blog/opentelemetry-genai-semantic-conventions/)

---

## 6. How this informs the roadmap

See [roadmap-6-months.md](./roadmap-6-months.md) and [milestones-and-exit-criteria.md](./milestones-and-exit-criteria.md) for the full sequencing. The stack choices above compress to five directives:

- **Phase 0 locks the transport.** The custom `httpx` `BaseTransport`/`AsyncBaseTransport` (capture+replay core, one hook for both OpenAI & Anthropic) is the first thing built and the thing everything else depends on. Get bit-exact SSE record→replay working before anything else.
- **Ship the boring, permissive core first.** SQLite (WAL) + `zstandard` + `blake3` + `time-machine` + Typer/Rich are all mature and permissively licensed — no research risk. E2E must work on this stack alone.
- **Buy the waterfall, don't build it.** Reuse Perfetto UI (client-side, zero-server) plus OTLP export for v1; defer any FastAPI/React frontend until after E2E.
- **Own the schema; treat OTel as an edge concern.** Because GenAI semconv is unstable and unversioned, our internal recording schema is the source of truth and OTel is normalized in at ingest — this is a non-negotiable, not a preference.
- **ML is deferred and non-blocking.** `sentence-transformers` (bge-small) → `sklearn` HDBSCAN → optional UMAP is the whole Phase-2 clustering path; `snorkel`/`peft`/`unsloth`/`trl`/`ollama` stay out of the dependency graph, and **LoRA is a stretch / cut-line** that must never gate a milestone.
