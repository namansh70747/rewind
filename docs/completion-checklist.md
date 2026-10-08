# Completion checklist: implementation versus acceptance

The Week 1–26 implementation candidate is runnable. The original roadmap's final
Definition of Done is not yet met. A local test pass, a self-declared provenance
field or a ZIP does not establish live-fleet quality or a reviewed public release.

## Run the local acceptance pass

```bash
uv sync --frozen --extra dev --extra docs --extra integrations --extra tui --extra ml
uv run python scripts/validate_candidate.py
```

This executes lint, format checks, strict typing, the regression suite with
coverage, strict docs, wheel/sdist build, and a fresh wheel installation with 150
offline replay checks plus evaluation. Logs are under `.rewind/acceptance/`.
`local_checks_passed` and `release_check_passed` are deliberately separate fields.
The command exits nonzero on local failure; release readiness is independently
reported and must pass `fr release-check` before publication.

## Required inputs and what happens next

| Input / access | Work already prepared | Acceptance still required |
|---|---|---|
| GitHub repository-scoped installation: configured | Candidate published in draft PR #43; CI matrix, Pages and release workflows | Obtain Code Owner review, pass current remote checks and merge |
| Locally configured `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, with an explicitly chosen account model | `examples/provider_corpus.py`: three provider calls plus two local tools per recording, then offline verification | Capture and inspect 10–15 recordings per intended provider; live streaming/diversity remain separate coverage requirements |
| Authorized real fleet recordings and original trusted scripts | Checksummed import, fixture manifest evaluation, MCP capture, query DSL, vector search and maps | Hundreds of author-fleet runs; coverage across intended tools/providers; privacy review |
| Reviewed task-grouped failure labels and an independently collected prompted baseline | Grouped train/validation/test classifier and held-out baseline comparison | Meet the roadmap's held-out accuracy gate without leakage; human cluster and neighbor review |
| Agreed workload budgets and platform runners | Synthetic benchmark, Linux evidence, Windows/macOS wheel jobs | Actual-workload capture/storage/snapshot measurements and remote platform evidence |
| Maintainer format/spike approval, package ownership and publisher configuration | Release notes, evidence checklist, protected publication workflow | Approve ADRs, protect environments, verify distribution name, tag and publish reviewed code |

No credentials should be placed in the repository or submitted in chat. Account
keys are configured in the machine where the live corpus is executed.

## Controlled live-provider corpus

These commands make **three billable model calls per recording**. The model must
be one supported by your account and compatible with the selected SDK API. The
script stops after the first capture error and retains partial evidence.

```bash
uv run python examples/provider_corpus.py openai YOUR_CHAT_MODEL --output .rewind/openai-corpus
uv run python examples/provider_corpus.py anthropic YOUR_MODEL --output .rewind/anthropic-corpus
```

Each recording has three model boundaries and two explicitly local tools.
The generated agent scripts, portable recordings, fixture manifest and result
report remain together. Replaying makes no additional provider calls. The default
is ten recordings with fifty replays each. Output directories must be empty so
old evidence is preserved. These are controlled live-provider prompts; they do
not substitute for the author's real failing agent, multi-server fleet or
live-stream corpus.

## Real-corpus fixture gate

Place trusted original agent scripts and reviewed exports beneath one directory:

```json
[
  {"recording": "run-01.json", "script": "agent-01.py"},
  {"recording": "run-02.json", "script": "agent-02.py"}
]
```

```bash
fr eval-fixtures path/to/fixtures.json --n 50 --output .rewind/real-corpus-evaluation.json
```

The gate validates the full manifest before execution, rejects duplicate fixtures
and paths escaping its directory, checks recording integrity and source hashes,
and reports each failure explicitly. Recorded fingerprints, replay counts and
boundary counts are retained. A valid recording is evidence of capture/replay,
not a signed attestation of where it came from. Inspect provenance separately.
Only execute scripts you trust; Python replay isolation is not an OS sandbox.

## Scope decisions that need explicit review

- HTTP capture covers decoded UTF-8/JSON/SSE, not arbitrary binary/compressed wire
  packets or exact real-time scheduling. Request headers are not part of matching.
- Replay reconstructs observable boundary/application state, not arbitrary process
  heaps, threads or existing external checkpoints. Subprocess wrapping is unsupported.
- Managed MCP supports the qualified v1 lifecycle; server-initiated callbacks and
  SDK v2 are not implemented.
- Cluster narration now selects recorded feature IDs and renders fixed prose.
  This prevents invented free-text narratives from being accepted. Selected-feature
  relevance and real-fleet coherence still need human review; no causal claim is made.
- LoRA was explicitly cut under the roadmap's permitted scope-cut decision.

These limits are part of the supported contract. They cannot be marked implemented
merely by passing an unrelated synthetic test or changing a checklist status.

## Additional local evidence

The [actual local-model demo](local-model-demo.md) adds 200 server-off replay
checks and an explicit decision intervention over captured model output. Its tools
remain simulated; it does not replace real fleet, account-provider, human-review
or publication gates. The observed price-only live fork did not recover.
