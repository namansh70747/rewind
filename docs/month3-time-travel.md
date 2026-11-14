# Month 3: time travel and counterfactual forks

The [planner audit](validation/month3/planner-audit.md) maps every week 10–13
requirement to implementation, tests and evidence. [ADR-0011](adr/0011-month3-logical-state-and-checkpoints.md)
defines the logical-state and derived-checkpoint contracts without changing the
frozen boundary-log format.

## Inspect and scrub

```bash
uv sync --frozen --extra integrations --extra tui --extra dev
uv run fr show RUN_ID --at 5
uv run fr snapshot RUN_ID 5
uv run fr tui RUN_ID
uv run fr trace-export RUN_ID trace.json --format perfetto
uv run fr trace-export RUN_ID trace.otlp.json --format otlp
uv run fr trace-export RUN_ID trace.pb --format otlp-protobuf
```

Inspection schema version 1 includes the boundary's request, response and chain
hash, observed values, the latest explicit logical agent state, and reconstruction
counters. Final output is hidden until the last boundary. The terminal pins the
step and chain above a scrollable JSON view; left/right navigate, Home/End jump
to the first/last step, and PageUp/PageDown scroll details. Forks are prominently
quarantined as best-effort what-if experiments.

`show --at` reuses CAS checkpoints across invocations. The first inspection of an
unindexed run validates and indexes the log in O(N); later queries restore the
nearest checkpoint and apply fewer than k suffix events. The default k is
floor(sqrt(N)), at least 1. CAS manifests store changed references with sparse
full anchors and bounded delta ancestry. Returning a large state still incurs
its copy cost. In-memory SnapshotIndex similarly builds once and serves repeated
queries. State means declared logical values, not an arbitrary Python heap.

```bash
uv run python scripts/benchmark_month3.py
uv run python scripts/month3_corpus_review.py recording1.json recording2.json --output .rewind/corpus-review
uv run --with perfetto python scripts/validate_month3_perfetto.py .rewind/corpus-review/*.perfetto
```

The corpus review compares intervals 1, sqrt(N) and N with a separate sequential
state reference. It inspects all steps in both directions in the terminal.
Benchmarks report cold builds separately from warm queries and do not impose
machine-dependent CI latency thresholds. See the audit for results on real
provider recordings and the long-run fixture.

## Fork a recorded script

```bash
uv run fr record -- python agent.py
# value.json contains the whole replacement boundary response.
# @tool example: {"ok": true, "value": 420}
# mocks.json contains optional explicit fixtures: {"tool/reserve": RESPONSE}
uv run fr fork RUN_ID --source agent.py --at 3 --value value.json --mocks mocks.json
```

The original source hash must match. Rewind replays the prefix, replaces exactly
one response, simulates later known tools from their recorded outcomes by
occurrence, and saves a separate quarantined child. Recorded tool outcomes are
simulations even when new arguments differ; they do not establish that a real
reservation/charge succeeded. Explicit mock values override these fixtures.
Unknown tools, exhausted fixtures and unspecified external I/O fail closed.

For a selected live continuation, edit a manifest and pass it explicitly:

```bash
uv run fr policy-set policy.json http /v1/chat/completions --no-mutating --live
uv run fr fork RUN_ID --source agent.py --at 3 --value value.json --mocks mocks.json --policy policy.json
```

Every live entry authorizes the named producer. Classification as read-only
alone does not authorize execution; unknown tools default to no live execution.
Mutating tools need an explicit per-tool live entry to run. The existing
`fr fork RUN_ID --price 420` travel demo remains supported. Verify script children
with `fr verify-script`; their boundary logs are replayable even though forks
are best-effort exploration of changed behavior.

Python APIs: `fork_run`/`afork_run` require explicit continuation mocks;
`fork_with_policy`/`afork_with_policy` additionally accept SideEffectPolicy.
`recorded_tool_mocks` constructs fresh occurrence-aware simulation fixtures.
`evaluate_forks` changes one intervention at a time, recreates fixtures per
trial, verifies every child and records an application-defined score with parent
provenance. See [experiment evidence](validation/month3/fork-experiments.json).

The policy mediates trusted producers. It is not an OS sandbox for arbitrary
filesystem/subprocess/native-extension side effects. Concurrent capture is
supported through ConcurrentSession; fork execution is serialized.

## LangGraph checkpoints and callbacks

`run_graph` and `arun_graph` accept `callbacks=True` and a native thread config.
RewindCallback records declared completion/error outputs, preserving thread and
node labels while excluding random framework run IDs. The handlers run inline
inside the async event loop.

`capture_checkpoint` / `acapture_checkpoint` read logical values and the next-node
frontier from an existing graph checkpointer. `restore_checkpoint` /
`arestore_checkpoint` can seed a fresh native checkpointer from this evidence;
the caller supplies `as_node`, and the resulting frontier must match before any
continuation executes. Supply `inputs=None` when resuming a native checkpoint.
Opaque framework IDs and arbitrary runtime objects are not serialized.

The tests compare native checkpoint resume with Rewind replay: native resume
re-executes the later external producer, while six exact Rewind replays and the
safe fork invoke no producers. [Measured comparison](validation/month3/native-resume-comparison.json).
A real two-branch async LangGraph test records fast-before-slow completion and
replays that schedule without executing either async producer.

## Live NVIDIA/Gemini gate and trace viewers

```bash
uv run python examples/month3_langgraph.py
# With provider keys configured in the process environment:
uv run python examples/month3_langgraph.py --live --output .rewind/month3-live
# One provider/model can be selected independently:
uv run python examples/month3_langgraph.py --live --provider gemini --model gemini-3.5-flash-lite --output .rewind/gemini-live
```

The example uses a fresh InMemorySaver thread per execution, native callbacks,
logical checkpoint capture, a changed quote, allowlisted live model continuation
and an explicitly mocked reservation. Both parent and child replay three times
offline. Both real providers passed this expanded gate; metadata-only reports
are committed, and credentials/full model recordings are excluded.

Perfetto opens the complete-slice JSON directly; the official trace processor
loads these files unchanged and checks every slice with zero parser errors.
OTLP JSON/protobuf are submitted unchanged to Jaeger's collector; its query API
and browser validate stored spans, chain hashes and fork provenance. HTTP model
boundaries are classified as OpenInference LLM spans with JSON input/output.
Trace import retains external spans as observational, non-replayable evidence.
Timestamps in these exports are explicitly ordinal.

PR CI runs deterministic tests, corpus navigation, Perfetto and Jaeger/browser
checks. Repeated paid live runs are opt-in with repository variable
`REWIND_LIVE_VALIDATION=true` plus the two Actions secrets, or an explicit manual
workflow run. Missing credentials fail a requested live run; a skipped live job
is never counted as new live evidence. Local two-provider acceptance evidence is
linked in the planner audit.
