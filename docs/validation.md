# Validation record — local alpha 0.1.0

Executed on Python 3.12.14 in the development environment on 2026-10-08.
These are synthetic/local results, not production-provider qualifications.

| Check | Observed result |
|---|---|
| Python regression suite | 107 passed on Python 3.11.17, 3.12.14 and 3.13.16 (Linux), including all 26 pre-existing tests |
| Coverage | 81% combined statement/branch coverage after acceptance hardening |
| Ruff lint and format | Passed |
| Strict mypy | Passed, 55 checked source/test files |
| Bundled demo | 3 runs × 50 replays; identical output/fingerprint per run |
| Synthetic evaluation | 12 price cases × 10 replays; expected original outcomes and successful recovery |
| Trusted script example | Captured HTTP + stdout, 10 verified replays |
| Distribution | sdist and wheel built with `uv build` |
| Browser acceptance | Desktop/mobile timeline, search, snapshots, aligned insert/delete/reverse comparison, lineage; zero JS errors and HTTP requests |
| Clean wheel installation | Fresh venv installed wheel; complete demo and HTML generation passed |

The demo and evaluation commands emit actual results; no benchmark numbers are
hardcoded into the application UI. Regenerate them with `fr demo` and `fr eval`.

## Latest acceptance hardening

The single-command acceptance runner passed all seven local checks: lint, format,
types, **107 tests**, strict docs, distribution build and clean wheel smoke. This
latest complete pass ran on Python 3.13.16; all 107 tests also passed on 3.11.17 and 3.12.14.
New tests reject unknown/duplicate evidence IDs and model-written claims, corrupted
fixtures, malformed/duplicate/path-escaping manifests and script runtime failures.
The live-provider corpus generator passed controlled five-boundary SDK capture and
offline replay for both OpenAI and Anthropic. Neither account key is configured,
so no claim of live-provider corpus completion is made.

Actual local Ollama inference passed the new evidence-selection-v2 contract on
three synthetic clusters. Displayed explanations are now rendered exclusively
from selected recorded feature labels/weights, replacing the earlier invented
free-text claims. Real-fleet relevance and independent human review remain pending.

## Regression risks explicitly covered

- Mutating requests/responses cannot alter already-recorded evidence.
- Corrupted responses, sequence numbers, terminal fingerprints and truncation fail.
- Forks never invoke original boundary producers; unspecified mocks fail closed.
- Intermediate timeline inspection cannot expose future outputs or state snapshots.
- JSON export detects changed final output; HTML escapes script-breakout payloads.
- Atomic SQLite rollback does not leave a partial run after metadata serialization fails.
- Replay blocks an ordinary unmediated socket connection and restores socket methods.
- UTF-8 split across SSE chunks survives, while secret redaction remains applied.
- Script source drift is rejected; replay checks redacted stdout as well as boundaries.

## Limits of this evidence

Live OpenAI/Anthropic/NVIDIA accounts were not used. The original suite uses mock
provider transports; the teaching demo uses simulated tool/LLM services. Opt-in async completion ordering has controlled tests; arbitrary concurrency,
native networking, subprocesses, full PII coverage and production workloads are not qualified. The socket guard is not a security sandbox. Remote CI is now running on draft PR #43; use the checks on its latest commit for current status.

## Roadmap expansion checks

Actual SDK objects with controlled HTTP transports, LangGraph record/replay/fork,
OTLP protobuf-schema parsing, Textual pilot navigation, 20 secret seeds, recorded
transport failures, persisted concurrent tools, snapshots/GC, policy gates, fixture
evaluation and grouped JSON classifier inference are covered. The actual BGE-small CPU model, LanceDB persisted cosine search, HDBSCAN/UMAP and
semantic alignment passed a separate smoke test on 15 synthetic recordings. No
production accuracy or human cluster coherence is inferred.

The synthetic 1,000-event benchmark is emitted by `fr benchmark`; it is an observation
on this environment, not a production performance acceptance threshold. See the
[26-week ledger](roadmap-status.md) for gates not yet satisfied.

The managed MCP tests start actual official SDK stdio and Streamable HTTP servers,
then stop the server and replay without additional calls. Async LangGraph uses a
fresh InMemorySaver for each run. Quoted/escaped/multiline credential regressions,
byte-preserving safe SSE chunks, source/concurrency script metadata and explicit
policy-manifest parsing are covered.

Qualified embedding model: `BAAI/bge-small-en-v1.5` revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, loaded locally on CPU. Full local model
content fingerprint: `55d82df3eec1e93c6890ed36a0914375e374b7fccfc33e25026cf7393ef4856f`.
Run `examples/embedding_smoke.py` after the pinned setup in the integration guide.

Fresh locked environments on Python 3.11 and 3.13 also passed the bundled demo
(three runs × five replays each). This is local Linux matrix evidence, not remote
GitHub CI or Windows/macOS qualification. Core wheel smoke on Python 3.12 runs
three recordings × 50 replays. SOCKS support is now an explicit runtime dependency.

## Week-26 preparation checks

- Official Perfetto TraceProcessor 57.2 (Python package 0.58.2) imported seven
  boundaries from the unchanged JSON export.
- Phoenix 20.19.0 rejected JSON with HTTP 415, so standard OTLP protobuf export was
  added. Phoenix accepted those unchanged bytes with HTTP 200, persisted all seven
  spans and displayed the trace's names and recorded input/output in Chromium.
- Ordinal timestamps map to January 1970. Open the trace directly or adjust the
  viewer time filter; they are not represented as measured execution timestamps.
- Scoped redaction, paced synchronous/asynchronous chunks, local-Ollama API/schema
  handling and missing/tampered release-evidence rejection have regression coverage.
- Actual Ollama 0.40.1 CPU inference with official Qwen2.5-0.5B Q4_K_M generated
  three schema-valid cluster summaries on 15 synthetic recordings. The downloaded
  GGUF SHA-256 matched its upstream LFS digest at a pinned revision. Inspection
  found unsupported causes and repetition, so the free-text design was **not passed** and was replaced as described above.
  Full model identity, outputs and findings are in `release-evidence/ollama-qualification.json`.
- Portable clean-wheel smoke passed on Linux: isolated installation, installed CLI,
  150 replays and evaluation. Windows/macOS jobs are prepared, not executed.
- After this hardening, all 97 tests and strict mypy passed again on Python 3.13;
  the previous complete 3.11/3.12 matrix evidence remains above.
- Release and Pages workflows are prepared but have not run remotely. The evidence
  checklist remains blocked until missing real data, approvals and publisher access exist.

## Actual local-model replay and intervention

Four recordings from the controlled local Ollama scenario each replayed fifty
times after the server was stopped (200 exact replay checks). The model wrongly
rejected an affordable price; a price-only live fork also failed. A separately
labelled model-answer intervention recovered through mocked reservation tools.
The model error remains preserved and is not claimed fixed. Browser checks passed
for recorded-model/simulated-tool provenance, explicit intervention lineage, final
output, desktop/mobile layout and offline behavior. See [actual local-model demo](local-model-demo.md)
and `release-evidence/local-agent-qualification.json`.

## GitHub publication and Windows regression

The candidate is published in [PR #43](https://github.com/namansh70747/rewind/pull/43).
The first GitHub run passed Linux Python 3.11–3.13, lint, strict docs and CodeQL.
Its Windows wheel job found that redirected cp1252 output cannot encode help
arrows. The CLI entry point now preserves the terminal encoding and uses
backslash escapes for unsupported characters. A subprocess help/demo regression
reproduces that terminal constraint. Updated local acceptance passes 108 tests,
lint, formatting, types, strict docs, package build and clean-wheel smoke.
The platform checks on the current PR revision remain the authoritative remote
qualification; a successful Linux run alone does not qualify Windows/macOS.
