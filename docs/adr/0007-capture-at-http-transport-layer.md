# ADR-0007: Capture at the HTTP transport layer, not the instrumentation layer

- **Status:** Accepted
- **Date:** 2026-08-08
- **Deciders:** Naman Sharma, @aasthaaa25, @kartikdua24

## Context

To play back a run bit-for-bit ([ADR-0006](0006-replay-is-playback-not-re-execution.md)),
Rewind must record the *exact* bytes of every LLM and tool response — including HTTP
headers that affect behavior, Server-Sent-Event (SSE) chunk boundaries and ordering,
partial tool-call JSON, and mid-stream errors.

There are two candidate interception points, evaluated in
[`../plan/tech-stack-and-oss-map.md`](../plan/tech-stack-and-oss-map.md):

- **The instrumentation layer** — OpenTelemetry GenAI / OpenInference / OpenLLMetry
  emit spans with prompt/response *as attributes*. This capture is opt-in, frequently
  truncated, and drops raw bytes, header ordering, and SSE framing. It is lossy by
  design — sufficient to *render* a run, insufficient to *replay* one.
- **The HTTP transport layer** — both the OpenAI and Anthropic Python SDKs are built on
  `httpx`, which exposes a pluggable `BaseTransport` / `AsyncBaseTransport`. A single
  custom transport sees the raw request and the raw response stream for both providers.

## Decision

**We will capture at the `httpx` transport layer as the source of truth for replay, and
use OpenTelemetry/OpenInference only for the presentation/semantic layer.**

- A thin custom `httpx` transport records byte-exact requests and responses (including
  per-frame SSE chunks and inter-chunk timing) into the recording. One hook covers
  OpenAI and Anthropic; MCP is captured analogously at its JSON-RPC transport frames.
- Instrumentation libraries (OpenInference/OpenLLMetry) are consumed to build the
  human-facing timeline/tool-tree and to interoperate — never as the replay source.
- Determinism boundaries that are *not* HTTP (clock, RNG, uuid, env) are captured with
  dedicated shims, not via the transport.

## Consequences

- **Easier:** byte-exact replay of streaming responses becomes possible; two providers
  are covered by ~one interceptor; we are insulated from the churn and lossiness of the
  (still-unstable) OTel GenAI conventions.
- **Easier:** we still get a rich semantic timeline "for free" by *also* reading OTel/
  OpenInference spans for presentation.
- **Harder / obligations:** we own HTTP edge cases (retries, connection pooling,
  redirects, header scrubbing) ourselves; we must scrub `Authorization`/API-key headers
  before anything is persisted; SDKs that bypass `httpx` (or use a non-standard client)
  need a dedicated adapter.
- **Risk:** a provider SDK that stops using `httpx` would require a new capture path —
  mitigated by keeping the interceptor behind an interface.

## Alternatives Considered

- **Capture via OpenTelemetry/OpenInference attributes.** Rejected: lossy, truncated,
  opt-in — cannot reconstruct raw/streamed bytes needed for bit-exact replay. (Kept for
  presentation and interop.)
- **`vcrpy` cassettes.** Rejected as the core engine: its `httpx` + async + streaming
  path is historically unreliable — a dealbreaker for LLM SSE — though it remains a
  useful reference and a fine tool for non-streaming smoke tests.
- **A capture proxy (mitmproxy-style) in front of the agent.** Deferred: valuable as a
  future *zero-instrumentation* fallback, but heavier and out of scope for the core
  in-process capture path.
