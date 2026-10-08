# Integration and qualification guide

Install `pip install -e '.[integrations,tui,ml]'`. The integration dependency set pins
MCP v1, OpenAI v1 and Anthropic's httpx-based SDK line; it does not promise support
for every future SDK major. All recorded services below are trusted application code.

## Managed MCP connections

```python
import asyncio
from flightrecorder.boundary import Cassette, Session
from flightrecorder.integrations.mcp_client import mcp_stdio, mcp_http


async def agent(session):
    async with mcp_stdio(session, "calculator", "python", ["my_server.py"]) as client:
        tools = await client.list_tools()
        result = await client.call_tool("add", {"a": 20, "b": 22})
        return result
    # For a remote server, use:
    # async with mcp_http(session, "calculator", "http://localhost:8000/mcp") as client:
    #     result = await client.call_tool("add", {"a": 20, "b": 22})


session = Session("record")
result = asyncio.run(agent(session))
recording = Cassette(session.boundaries, session.chain)
replay = Session("replay", recording)
assert asyncio.run(agent(replay)) == result
replay.assert_fully_consumed()
```

The official SDK owns process/HTTP lifecycle, initialization, protocol negotiation
and cleanup. Rewind records initialization, tool listing and tool calls as atomic
boundaries. Replay does not import the SDK, launch a subprocess or contact a server.
Recording headers/environment values are supplied at runtime and are not persisted.
Executable arguments and URL are redacted and matched as configuration evidence.
Only launch executables and contact endpoints you trust.

Tool `isError` is retained in the returned protocol result. JSON-RPC and transport
exceptions are represented as `MCPToolError` consistently on record and replay.
Server-initiated sampling/elicitation callbacks and MCP SDK v2 are not supported.
Real local stdio and Streamable HTTP server tests cover initialization, list, call,
tool errors, teardown and offline replay with the server stopped. This is not a
qualification of the author's 672-tool production fleet.

## LangGraph

`run_graph` and `arun_graph` consume compiled graph `values` streams and record explicit
state evidence, plus supported decorated-tool/httpx boundaries inside graph nodes.
Use a fresh in-memory checkpointer or a fresh isolated thread for each replay.
The async acceptance test uses an actual `InMemorySaver`; Rewind does not yet restore
an arbitrary pre-existing graph checkpoint database or Python process heap.

Run `python examples/langgraph_agent.py` for a keyless 50-replay example.

## Script concurrency and source capture

```bash
fr record-script agent.py --concurrent --sources
fr verify-script RUN_ID agent.py --n 50
# Equivalent supported entrypoint form:
fr record --concurrent --sources -- python agent.py
```

Script metadata retains these choices through save/load, so replay uses the same
contract. The source digest covers the entrypoint file, not all dependencies.
Concurrent sessions require stable task-start order and capture terminal successes,
producer exceptions and cancellations. Errors replay as `RecordedBoundaryError`;
original exception names/messages remain evidence. Arbitrary task cancellation timing,
threads and multiprocessing are not promised. Forking concurrent scripts remains
explicitly rejected. Sequential scripts with source shims can be forked safely.

## Compare different-length trajectories

`fr diagnose A B` emits aligned raw evidence and weak divergence labels. Generated
HTML dashboards now include selectable aligned rows with absent-step placeholders;
selecting either direction keeps baseline/candidate indices correct. The default
alignment uses structured and lexical inputs; `fr diagnose A B --model LOCAL_DIR`
and `fr dashboard A B --alignment-model LOCAL_DIR` enable local embedding cosine.
Response content does not influence alignment. A one-million-cell budget avoids
unbounded matrix allocation; oversized dashboard comparisons display the limitation.

## Classifier versus a prompted baseline

`fr train-classifier labels.json --output classifier.json` records group-disjoint
splits, test predictions with stable IDs and a dataset digest. Collect baseline
predictions independently using a fixed prompt/model; retain provider/model/prompt
hash provenance. Do not tune the prompt or model on test labels.

```json
{
  "provenance": {
    "provider": "YOUR_PROVIDER",
    "model": "EXACT_MODEL",
    "prompt_sha256": "SHA256_OF_FIXED_PROMPT"
  },
  "predictions": [{"id": "HELD_OUT_ID", "label": "TAXONOMY_LABEL"}]
}
```

```bash
fr compare-baseline classifier.json baseline.json --output comparison.json
```

The command requires exactly one prediction for every held-out ID, rejects missing
or duplicate rows and reports macro F1 and per-class metrics. It does not make API
calls or certify the provenance of user-submitted predictions. The real-data gate
remains open until reviewed labels and independently collected baseline results exist.

## Trace exports and docs

OTLP JSON is validated against the official protobuf schema. Perfetto exports use
Trace Event JSON. Both explicitly mark ordinal timestamps, not fabricated timings.
External-viewer acceptance remains a separate gate. OTLP ingestion produces
non-replayable observational evidence.

`mkdocs build --strict` creates a navigable documentation site. GitHub Pages deployment
requires an authorized repository connection and Pages setup; a local build alone is
not a live published website.

## Qualified local embedding workflow

The BGE-small CPU path, persisted LanceDB cosine search, HDBSCAN, UMAP and semantic
alignment were executed successfully on 15 synthetic recordings. Human cluster
coherence and real-fleet performance are not inferred from that smoke test.

For CPU-only setup with uv:

```bash
uv pip install --torch-backend=cpu -e '.[embeddings]'
```

Download the model once, then all Rewind embedding operations use local files only:

```python
from huggingface_hub import snapshot_download

snapshot_download(
    "BAAI/bge-small-en-v1.5",
    revision="5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
    local_dir="models/bge-small",
    allow_patterns=["*.json", "*.txt", "*.safetensors", "1_Pooling/*"],
)
```

```bash
python examples/embedding_smoke.py models/bge-small
fr index-embeddings models/bge-small --output .rewind/embeddings.json
fr search-embeddings RUN_ID .rewind/vectors TABLE_NAME models/bge-small
```

The index report gives TABLE_NAME. Model weights, tokenizer and config are hashed;
querying an index with different model contents fails. Weights are not bundled in
the source ZIP. The public model is downloaded separately at the pinned revision.

## Explicit policy manifest

```bash
fr policy-set policy.json tool search --no-mutating
fr policy-set policy.json tool reserve_trip
```

Both entries remain mocked by default. `--live` writes an explicit allowlist entry,
but the editor never executes a tool. Applications parse it with
`policy_from_manifest` and enforce authorization before `fork_with_policy`.
Read-only classification does not grant live permission.
