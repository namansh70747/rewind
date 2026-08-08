# Spike A — bit-exact playback (the go/no-go)

> **Throwaway spike.** Not the real `flightrecorder` package. Its only job is to answer
> the question everything else depends on, *before* we build the real engine:
> **can a recorded agent run replay bit-for-bit, offline, with zero API calls — and can
> we prove it?**
>
> See [`docs/plan/risks-and-spikes.md`](../../docs/plan/risks-and-spikes.md) (Spike A/B),
> and ADR-[0006](../../docs/adr/0006-replay-is-playback-not-re-execution.md) /
> [0007](../../docs/adr/0007-capture-at-http-transport-layer.md).

## What it does

A tiny 3-step agent (three LLM calls at temperature 0.7, plus a clock read, a UUID, and
an RNG draw) is run through a `Session` that mediates every **boundary** — every value
the agent reads from the nondeterministic world. Capture happens at the **httpx transport
layer** (ADR-0007). Each boundary extends a **hash-chain**
`h_i = BLAKE2b(h_{i-1} ‖ canon(request_i) ‖ canon(response_i))`; the final value is the
run's fingerprint.

- **Record:** call the real world once, log every boundary.
- **Replay:** serve the recorded values, **never** call the network (the kill-switch),
  recompute the hash-chain, and raise `Divergence` — loud and localized — at the first
  mismatch.

## Run it

### The live go/no-go (needs an API key)

```console
$ export OPENAI_API_KEY=sk-...
$ uv sync --extra spike
$ uv run python -m spikes.spike_a record --n 50
```

This records **one** real run, then replays it **50×** offline. **PASS = 50/50 replays
byte-identical** to the recording (same output, same fingerprint) with zero API calls.
The recording is written to `spikes/spike_a/last_run.cassette.json` (git-ignored) so you
can re-verify it offline later:

```console
$ uv run python -m spikes.spike_a verify spikes/spike_a/last_run.cassette.json --n 50
```

### The offline proof (no key — this is what CI runs)

```console
$ uv run pytest tests/test_spike_a.py -v
```

The test uses a mock transport that behaves like a nondeterministic provider, then
proves: (1) replay is bit-exact 50×, (2) the oracle catches a tampered recording and
names the boundary, (3) a truncated recording underflows (kill-switch — no outbound
call), and (4) an input change (uncaptured nondeterminism / code drift) is caught.

## Pass / fail bar

| Outcome | Meaning | Next |
|---|---|---|
| **PASS** | Playback is faithful and provable. | Build the real walking skeleton (issues #16/#17). |
| **FAIL — silent divergence** | The oracle didn't catch a real divergence. | R3 is fatal until fixed; do not proceed. |
| **FAIL — can't reproduce** | Some nondeterminism isn't captured. | Enumerate the missing boundary, or narrow scope per the risk doc. |

## What this spike does *not* do (by design)

Streaming/SSE, concurrency, real tool-calling, multi-provider, redaction, storage/dedup —
all deferred to the real engine per the roadmap. This spike is the smallest thing that
tests the core bet, and it is meant to be deleted once the real recorder subsumes it.
