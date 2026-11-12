# Month 3 — time travel and counterfactual forks

Scope: weeks 10–13 of [the execution plan](plan/roadmap-6-months.md).
This builds on the existing snapshot store, Textual scrubber, LangGraph state
adapter and OTLP/Perfetto exporters rather than replacing the recording format.

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

`show --at` uses the snapshot reconstruction API and includes the boundary's
request, response and chain hash. State is boundary-observable evidence plus the
latest explicit `state` boundary, not an arbitrary Python heap. No future state
or final output is revealed before the last boundary. Left/right step through
the terminal view. Forks are visibly quarantined in the timeline and terminal;
trace exports carry counterfactual, parent and intervention provenance too.

SnapshotIndex builds once in O(N), then applies fewer than `k` suffix events per
query; its default interval is floor(sqrt(N)). Cold CLI invocations still build
an index. Returning state requires copying its payload; bounded suffix work is
not a claim of constant overall latency. The persisted `snapshot` command reuses
CAS-backed checkpoints across invocations.

```bash
uv run python scripts/benchmark_month3.py
```

The benchmark compares intervals 1, sqrt(N), and N, reporting cold index cost,
warm p50/p95, checkpoint count, exactness and maximum suffix length. It uses a
synthetic long run; it does not claim production-corpus performance.

## Fork a recorded Python script

```bash
uv run fr record -- python agent.py
# value.json is the complete replacement boundary response.
# For @tool outcomes: {"ok": true, "value": 420}
# mocks.json maps remaining boundary identities to JSON responses, for example:
# {"tool/reserve": {"ok": true, "value": "simulated"}}
uv run fr fork RUN_ID --source agent.py --at 3 --value value.json --mocks mocks.json
```

The original source hash must match. The prefix replays exactly, one response is
replaced, and every subsequent external boundary needs an explicit mock. Missing
mocks fail closed. The child is saved separately with parent fingerprint and
intervention step, and can be verified with `fr verify-script`. The original
`fr fork RUN_ID --price 420` travel-demo interface remains available.

For async agents, `afork_run(parent, async_run, at=..., value=..., mocks=...)`
awaits a callable accepting a Session. `afork_with_policy` additionally permits
explicitly allowlisted live producers. A supplied mock wins over an allowlist;
classifying a tool as read-only does not itself authorize execution. Unknown and
mutating tools remain blocked unless mocked or individually authorized live.
Async producers are serialized; concurrent recordings are rejected for forks.
Live continuation errors abort the fork rather than create a successful recording.

The policy covers mediated producers in trusted Python code. The Python socket
guard is not an OS sandbox, and filesystem/subprocess side effects outside
instrumented tools are outside its guarantee. Run trusted agents in isolation.
A fork is best-effort exploration, never a claim that the original future would
have happened. Its saved boundary log can still replay exactly.

## LangGraph + NVIDIA and Gemini

```bash
# Synthetic HTTP responses, no credentials or outbound calls:
uv run python examples/month3_langgraph.py
# Actual providers, with NVIDIA_API_KEY and GEMINI_API_KEY configured securely
# in the process environment (not in command arguments or source files):
uv run python examples/month3_langgraph.py --live --output .rewind/month3-live
# Validate one provider independently when only its credential is available:
uv run python examples/month3_langgraph.py --live --provider gemini --output .rewind/month3-gemini-live
```

The --provider option can be repeated; without it both providers are selected.
Only selected providers need credentials. Use --model MODEL with one --provider
to select another model available to your account. The live example makes two completion requests per provider: one for the parent
and one for its live fork continuation. Reservations are simulated in the parent
and explicitly mocked in the fork. It then verifies both recordings three times
offline, reconstructs all states and exports portable, Perfetto and OTLP files.
The output directory must be new so prior evidence is preserved. Recordings can
contain prompt and response content; inspect before sharing.

Gemini uses its [documented OpenAI-compatible endpoint](https://ai.google.dev/gemini-api/docs/openai).
The ordinary CLI also accepts `fr record --provider gemini`.

The adapter runs inside LangGraph's async event loop, capturing decorated tools,
httpx requests and streamed state snapshots. Use fresh graph/checkpointer thread
state for record/replay; arbitrary existing checkpoint memory is not restored.
Unlike native LangGraph checkpoint resume, Rewind replay serves external results
from its recording rather than calling models or tools again. A policy fork
replays the prefix and permits only selected producers after the intervention.
Parallel fork scheduling and native checkpoint restoration remain outside this
serialized adapter contract.

Perfetto opens the `*.perfetto` JSON as a Trace Event file. `*.otlp` is OTLP/HTTP
JSON and `*.otlp-protobuf` is its protobuf counterpart; send them to a compatible
collector's trace ingestion endpoint to inspect in Jaeger/Phoenix. Timestamps are
explicitly ordinal, not measured execution durations. Existing trace import is
observational, non-replayable evidence. Schema-level protobuf parsing is tested;
Jaeger ingestion, query round-trip and a Chromium trace-page check now run in the
Month 3 acceptance workflow. See the validation report for the recorded run.

## Validation evidence

See [the session report](validation/month3/report.md). Offline coverage runs in
CI, including an async LangGraph record→fork→replay, a terminal scrubber pilot,
script CLI intervention, policy precedence/cancellation and provider transport
round trips. Live validation requires configured credentials and is reported
separately from synthetic evidence.
