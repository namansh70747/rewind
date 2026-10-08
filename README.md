# Rewind

**Record a failure. Replay the evidence. Test a different decision.**

A local flight recorder and counterfactual debugger for Python AI agents.
Rewind captures external responses at supported boundaries, feeds those values back
into agent code offline, and finds where two recordings first diverge.

[![CI](https://github.com/namansh70747/rewind/actions/workflows/ci.yml/badge.svg)](https://github.com/namansh70747/rewind/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/License-Apache--2.0-green)](LICENSE)

**Status: working local alpha (0.1.0).** The offline investigation workflow is
implemented and tested. This is not completion of the original six-month research
roadmap. Capture coverage and safety limits are explicit below.

## Run the complete demo

Python 3.11+; no API key, account, GPU, or database server needed.

```bash
git clone https://github.com/namansh70747/rewind.git
cd rewind
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
fr demo
```

Open **`.rewind/demo.html`** in your browser. The HTML is self-contained and makes
no network requests. The command also creates three SQLite runs and portable JSON
recordings. Re-running the demo adds new runs; it never deletes prior recordings.

### What you will see

1. A travel agent receives a stale **720 INR** quote against a **500 INR** budget.
2. Its simulated reservation fails. Record and replay the failed run **50 times**.
3. Compare it with a passing run; the first differing response is **boundary #3**.
4. Fork the failed run at that boundary, replacing the quote with **420 INR**.
5. Execute the agent logic again using explicit safe mocks for the continuation.
6. The recomputed state changes and the simulated reservation succeeds.

All LLM and external tool services in this teaching demo are **simulated**. The
recording, replay, hash verification, persistence, divergence detection, and fork
execution are real. The same HTTP capture core is tested with mock HTTP providers;
live-provider compatibility is not implied by synthetic results.

## Features and actual scope

| Capability | Implemented behavior |
|---|---|
| Record/replay | Sync and async httpx clients created inside `capture`; serialized by default; opt-in async completion-order capture |
| Streaming | Buffered UTF-8 SSE, sanitized chunks; optional pacing from recorded offsets |
| Integrity | BLAKE3 boundary hash chain (legacy BLAKE2b readable), sequence/fingerprint checks, blob verification |
| Storage | SQLite, zstd-compressed BLAKE3 content-addressed blobs (legacy readable), atomic saves, fork provenance |
| Time travel | Inspect observed boundaries and explicit agent snapshots without future values |
| Counterfactuals | Replay exact prefix, intervene once, recompute using explicitly supplied mocks |
| Compare | Validated hash bisection, sequence alignment, divergence taxonomy |
| Dashboard | Search, scrubber, snapshots, side-by-side evidence, lineage, mobile layout |
| Portability | Versioned JSON with SHA-256 envelope checksum; validates before import |
| Scripts | Trusted `.py` entrypoints, httpx capture, source-file hash and redacted stdout verification |
| Evaluation | 12 labeled synthetic budget cases, replay and recovery checks |
| Similarity | Interpretable event-feature cosine similarity; **not** a learned diagnosis |

## CLI reference

Use run IDs printed by `fr demo` or `fr runs`.

```bash
fr runs
fr show RUN_ID
fr show RUN_ID --at 3
fr verify RUN_ID --n 50
fr bisect PASS_ID FAIL_ID           # exit 1 means a difference was found
fr fork FAIL_ID --price 420         # bundled travel scenario; safe mock continuation
fr dashboard FAIL_ID PASS_ID FORK_ID --output .rewind/investigation.html
fr export RUN_ID .rewind/run.rewind.json
fr import .rewind/run.rewind.json
fr similar RUN_ID
fr eval --n 10 --output .rewind/evaluation.json
fr doctor
```

Every store-oriented command accepts `--db PATH`. `fr verify` rebuilds the bundled
provider example or travel demo; arbitrary scripts use the explicit script command:

```bash
fr record-script examples/http_agent.py
fr verify-script RUN_ID examples/http_agent.py --n 10
```

Script recording runs **trusted code in your process**. It is not a sandbox.
There is no arbitrary subprocess command wrapper, and source drift checks cover
the entrypoint file, not all imported dependencies. Avoid module-global clients.

### Record a live example

```bash
# Set OPENAI_API_KEY in your shell or an untracked .env file first.
fr record --provider openai
# Also available: --provider anthropic or --provider nvidia
```

Live recording incurs the provider's usual charges. Offline demo/replay needs no key.
SOCKS proxy support is included in the runtime dependencies.

## Python API

```python
from flightrecorder import capture, verify_run


# Create httpx clients INSIDE this callable.
def agent():
    import httpx

    with httpx.Client() as client:
        return client.get("https://example.com").text


with capture() as cap:
    agent()
assert cap.cassette is not None
result = verify_run(cap.cassette, agent, n=5)
# verify_run checks boundary fingerprints, not callable return values.
print(result)
```

Explicit `Session` agents can also record `session.now()`, `new_uuid()`, `rand()`,
and `session.mediate('tool', name, request, producer)`. `record` / `verify` compare
both the final output and the boundary fingerprint. Record explicit `state`
boundaries to expose meaningful application snapshots in the timeline.

For custom counterfactuals, use `flightrecorder.fork.fork_run(parent, agent, at=N,
value=replacement, mocks={('tool', 'name'): callback})`. All effects must go through
Session; unspecified continuation boundaries fail closed. No original producer
runs after an intervention. See [the API example](examples/session_agent.py).

## Honest guarantees and limitations

- Replay is exact **relative to the sanitized, captured boundary values and the
  supported agent's output**, not compressed HTTP wire bytes, exact scheduler timing, or arbitrary
  process memory. JSON is normalized, bodies are UTF-8, headers other than content
  type are omitted, and known secret patterns are replaced before agent delivery.
- Redaction changes what the recorded agent sees. Known tokens, emails and named
  sensitive fields are scrubbed; arbitrary PII/secrets are not guaranteed covered.
  Explicit Session boundaries and outputs are application-managed. Review exports.
- Replay adds a best-effort Python socket guard. It is process-wide while active,
  not an OS sandbox: native networking, cached functions, files and subprocesses
  are outside it. Only execute trusted agents and trusted fork mock callbacks.
- Opt-in `capture(concurrent=True)` records async start/completion order; task-start
  order must remain stable. This is not arbitrary thread or process replay.
- `capture(sources=True)` instruments selected clock/RNG/UUID calls; cached aliases,
  independent RNG instances and pre-existing httpx clients remain outside coverage.
  Binary bodies, arbitrary headers and unwrapped non-httpx I/O are unsupported.
- “Time travel” inspects recorded evidence; it does not restore Python stacks/heaps.
- The first divergence is a **candidate explanation**, not causal proof. Sequence alignment uses structured/lexical costs by default and optionally local
  embedding cosine; neither establishes causality.
- Hash chains/checksums detect corruption, not malicious rewriting with recomputed
  hashes. There are no cryptographic signatures or external trust anchors.
- Optional LangGraph, MCP exchange, Textual, OTLP/Perfetto and offline fleet-analysis
  modules are implemented. External integrations have controlled local tests, not
  production fleet qualification. Embedding indexing needs separately installed
  dependencies and a local model; BGE-small/LanceDB/UMAP has a synthetic CPU smoke test.
- Real-provider replay gates, human-reviewed fleet evaluation, a prompted-LLM
  baseline comparison, production hardening and release publication remain open.

## Verification and faculty demo

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy
fr eval
```

The suite covers existing capture behavior plus safe forks, tampering, mutation
isolation, import/export, persistence rollback, script drift, network escape
attempts, dashboard injection and CLI acceptance. Optional browser checks:

```bash
npm install --no-save --package-lock=false playwright
npx playwright install chromium
fr demo
node tests/browser/dashboard.cjs
```

See [demo and viva guide](docs/demo-guide.md), [release validation](docs/validation.md),
and [implementation architecture](docs/implementation.md). Historical design and
six-month plans define acceptance gates; see the [week-by-week evidence ledger](docs/roadmap-status.md).

## Contributing and license

Apache-2.0. See [CONTRIBUTING](CONTRIBUTING.md), [SECURITY](SECURITY.md), and
[CITATION.cff](CITATION.cff). Inspired by record/replay debugging and Git bisect;
this project does not claim to be the first or only agent replay system.

## Roadmap implementation commands

Install tested optional workflows with `pip install -e '.[dev,integrations,tui,ml]'`.
The `embeddings` extra is separate and needs a local sentence-transformers model.

```bash
fr diagnose PASS_ID FAIL_ID
fr hash-bisect PASS_ID FAIL_ID
fr snapshot RUN_ID --at 3
fr query RUN_ID 'first response.status >= 400'
fr trace-export RUN_ID .rewind/trace.json --format perfetto
fr trace-export RUN_ID .rewind/otlp.json --format otlp
fr tui RUN_ID
fr storage-stats
fr fleet-map --output .rewind/fleet.json
fr benchmark
fr record -- python examples/http_agent.py
```

OTLP imports are explicitly **non-replayable observational traces**. Trace timestamps
are marked ordinal; exports do not invent measured wall-clock durations. Fleet maps
use an offline TF-IDF/HDBSCAN baseline. Supervised classification requires reviewed
`{text, label, group}` rows and uses disjoint train/validation/test groups. It reports
a majority baseline; superiority to an LLM has not been measured.

See [roadmap status](docs/roadmap-status.md) for every week, evidence and open gates.

Latest integration work: [managed MCP, async graphs, baseline comparison, policy
manifests and qualified embeddings](docs/integrations.md). The dashboard includes
aligned inserted/deleted steps. [Synthetic sample gallery](docs/gallery.md).

Release tooling now includes opt-in paced streams, custom redaction rules, local
Ollama cluster narration, OTLP protobuf export and a fail-closed evidence checklist.
See the [release execution guide](docs/release-guide.md). Prepared publishing workflows
require repository access, reviewed evidence and maintainer publisher setup.

### Finish acceptance from the candidate

Run `uv run python scripts/validate_candidate.py` after installing the documented
dev/docs/integrations/tui/ml extras. See [completion checklist](docs/completion-checklist.md)
for exact live-provider, real-fleet, review and publication requirements. This local
pass does not mark the original Week-26 release complete.

An [actual local-model example](docs/local-model-demo.md) now records real Ollama
inference, preserves an incorrect decision, tests a live price-change fork and
replays a separately labelled decision intervention with simulated tools.
