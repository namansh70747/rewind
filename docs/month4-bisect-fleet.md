# Month 4: bisect and MCP fleet

`fr bisect` and both comparison UIs share the validated diagnosis engine. It
separates the earliest raw mismatch from the first differing logical decision,
so a UUID or provider request ID does not become a fabricated model cause.

## Compare recordings

```bash
fr bisect PASS_ID FAIL_ID --json
fr bisect PASS_ID FAIL_ID --method align
fr compare-html PASS_ID FAIL_ID review.html
```

The arguments identify recordings in the local database (`--db` selects another).
Bisect exits 0 for identical evidence and 1 for divergence. Invalid recordings,
unsupported methods, and alignment-budget errors fail with a diagnostic. Use
`fr bisect --help` for the complete stable options. `--method hash` explicitly
asserts positional alignment and requires matching boundary kind/key sequences.
Auto mode selects hash search for compatible, unambiguous aligned input sequences;
other shapes use global sequence alignment. If repeated requests shifted between
runs, force alignment rather than assuming occurrence identity.

The JSON report contains `first_difference`, `first_diverging_decision`,
`primary_difference`, `upstream_context`, aligned index pairs and full raw events
plus JSON-pointer diffs. An inserted step has a missing baseline index; a removed
step has a missing candidate index. The HTML artifact shows both sides, supports
row selection, reversing baseline/candidate, keyboard activation, and jumping to
the correct source recording/index. Directional labels are recomputed on reversal.

Taxonomy candidates include `arg-hallucination`, `tool-choice`, `sampling-flake`,
`tool-result-drift`, `retrieval-drift`, `loop`, `cost-blowup`, and `truncation`.
These are weak labels inferred from observed fields, not verified causes.
Argument changes alone cannot establish hallucination. Identical model input with
changed output cannot establish that sampling rather than a provider/model change
caused it. Retrieval names and repeated requests are heuristic evidence.

## Semantic alignment using NVIDIA

Structured JSON similarity and lexical similarity work offline. To use actual
embedding cosine, explicitly capture vectors once with NVIDIA and reuse them:

```bash
# Configure NVIDIA_API_KEY in the process environment; never put it in a recording.
fr embed-pair PASS_ID FAIL_ID private-vectors.json
fr bisect PASS_ID FAIL_ID --embeddings private-vectors.json
fr compare-html PASS_ID FAIL_ID review.html --embeddings private-vectors.json
```

`embed-pair` sends canonical logical boundary inputs to NVIDIA's embedding endpoint.
Only use it for inputs you approve disclosing to that provider. Each event input
is capped at 4,000 characters, distinct texts are deduplicated, and requests are
batched. Defaults: `nvidia/nemotron-3.5-embed-1b`, passage embeddings, end truncation.
No other cloud model or provider is needed. A local embedding-model directory is
also supported by the Python API for already-installed offline models.

The cache excludes API keys and source text, binds vectors to both recordings and
their logical input hashes, validates counts/dimensions/finite nonzero values, and
supports reversed inputs. Vectors can still reveal information: keep caches
private. Bisect, HTML export and replay do not call an embedding API implicitly.

## Record a multi-server MCP agent

Install the `integrations` extra, then use public SDK transport seams:

```python
import asyncio
import json
import sys
from flightrecorder.integrations.fleet import MCPServer, open_fleet
from flightrecorder.replay import record, verify

servers = [
    MCPServer("catalog", "stdio", sys.executable, ["catalog_server.py"]),
    MCPServer("inventory", "streamable-http", "http://127.0.0.1:8000/mcp"),
]


def agent(session, transport):
    async def run():
        async with open_fleet(session, servers) as fleet:
            results = await fleet.gather(
                [
                    ("catalog", "lookup", {"item": "GPU"}),
                    ("inventory", "stock", {"item": "GPU"}),
                ]
            )
            return json.dumps(results, sort_keys=True)

    return asyncio.run(run())


recording = record(agent, concurrent=True, provider="mcp-fleet")
assert verify(recording, agent, n=50).passed
```

Use distinct, stable server names. The registry validates every specification
before launching anything, opens sessions in stable order, and closes all sessions
on failure. Per-server `env` (stdio) and `headers` (HTTP) stay runtime configuration.
Recordings contain redacted public SDK JSON-RPC request/response frames, including
`tools/call` method, ID and result/error. SDK auto-discovery can add `tools/list`
pairs within an operation. IDs are matched within each server; operation
occurrences distinguish repeated calls. Tool failures remain recorded evidence.

Replay uses recorded initialization/list/call outcomes without launching a server,
opening a socket, or reapplying effects. Old SDK recordings without `wire` still
replay; they cannot retroactively provide raw protocol evidence. Supported seams
are SDK stdio and streamable HTTP, not arbitrary raw TCP, legacy SSE, unmediated
clients, or every optional MCP feature. Notifications, server-initiated sampling,
progress timing and byte/chunk transport fidelity are outside this contract.

## Sequential and concurrent guarantees

Sequential `Session` replay requires exactly the recorded boundary sequence and
inputs. Opt-in `ConcurrentSession` records task start identities plus terminal
completion/error/cancel events. `asyncio.gather` returns values in argument order;
awaiting tasks observes their recorded completion order. The ordinary `record`
and `verify` functions persist and honor `metadata.concurrent`.

Task start order and mediated requests must remain stable. Completion ordering is
replayed without reproducing wall-clock delays. Async producers are not executed
on replay. Failures use `RecordedBoundaryError` with the original type/message as
evidence; cancellation uses `CancelledError`. A changed/incomplete fan-out fails
a bounded schedule wait (2 seconds by default) rather than hanging indefinitely.
Threads, arbitrary unmediated scheduling, external cancellation timing, callbacks
outside capture, and byte-identical process memory are not guaranteed. Concurrent
counterfactual forks remain explicitly unsupported.

Trusted script recordings include the Git commit, main source SHA-256, and loaded
local Python-module hashes. Verification/fork checks those hashes before executing
the script. Drift errors show `recorded @ SHA X, replaying @ SHA Y` and the changed
file. A documentation-only commit need not block playback if recorded sources
match. Dependencies outside the project, non-Python files, dynamic code, and
interpreter state are outside this source-provenance check.

## Reproduce acceptance

```bash
uv sync --frozen --extra dev --extra integrations --extra docs --extra tui --extra ml
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run mkdocs build --strict
uv run python scripts/validate_month4.py --output .rewind/month4-new --replays 50
uv run --with playwright python -m playwright install --with-deps chromium
uv run --with playwright python scripts/validate_month4_browser.py
# Optional live NVIDIA check: public, hand-authored synthetic inputs only.
uv run python scripts/validate_month4_embeddings.py --output .rewind/embeddings-new
```

The actual provider pair review script defaults to offline diagnosis. Its optional
`--embed` flag discloses recorded inputs and needs separate approval. No private
recordings, vector caches, raw prompts, or keys belong in committed evidence.
See the [planner audit](validation/month4/planner-audit.md) for measured results and
the remaining human review gate.
