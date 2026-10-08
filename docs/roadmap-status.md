# Roadmap evidence ledger — weeks 1–26

Updated 2026-10-08. This is an implementation candidate, **not a declaration that
all 26 weekly exit criteria passed**. The original roadmap requires CI evidence and
real recordings. Local synthetic tests cannot substitute for those gates.

Repository-scoped GitHub access is now configured. The candidate is published on
`feat/rewind-demo-release` in [draft PR #43](https://github.com/namansh70747/rewind/pull/43).
The PR now tracks the updated candidate. Remote CI, strict docs and CodeQL pass
on `beecba4`; Python 3.11–3.13 tests and clean-wheel checks on Ubuntu, Windows
and macOS are qualified. The Windows terminal defect is fixed and regression-tested.
See [machine verification evidence](release-evidence/github-ci-qualification.json).
No tag or release was created; independent Code Owner review and real-data gates
remain open. Evidence applies to the cited commit, not automatically to future changes.

| Week | Theme | Implemented / local evidence | Remaining gate or scope limitation |
|---|---|---|---|
| 1 | Real-provider replay | 50× synthetic demo; real SDKs with controlled transports | Live five-boundary provider corpus harness prepared and SDK-tested; execution needs credentials, plus real-corpus review |
| 2 | Spikes / go decision | Concurrency, source shims, secret seeds and mutation regressions | CPU/GPU measurements, complete spike report and approved ADR |
| 3 | Capture / store / CLI | HTTP, @tool, selected source shims, SQLite/CAS, trusted Python entrypoint | General subprocess wrapping deliberately unsupported |
| 4 | Playback / verify | Offline replay, fail-loud oracle, script fixture gate | Remote CI and real-corpus M1 gate |
| 5 | Divergence oracle | BLAKE3 chain, canonical JSON, integrity validation | Corpus-wide no-silent-divergence evidence |
| 6 | Streaming | Sanitized UTF-8/SSE, safe byte-exact chunk preservation, order and offsets; escaped/multiline credential regression | Compressed-wire/binary fidelity and live tool-stream corpus; opt-in timing playback now implemented |
| 7 | Providers / retries | OpenAI and Anthropic SDK tests; transport errors and retries; config_read | Live provider diversity and arbitrary config interception |
| 8 | CAS / format | BLAKE3/zstd dedup, GC, v2 export and legacy reads | Format ADR approval/merge and real footprint budget |
| 9 | Redaction / coverage | 20 seed-secret regression; Python socket audit catches swallowed errors | Real stored-corpus scan and broader I/O; configurable extra key/literal redaction now implemented |
| 10 | Snapshots | Sqrt-N checkpoints, immutable state views, persisted CAS checkpoints; invalid explicit intervals rejected | Real long-run latency budget; not process-heap restoration |
| 11 | TUI / Perfetto | Textual scrubber; actual Perfetto TraceProcessor accepted all seven demo boundaries | Real-corpus usability and interactive Perfetto UI review |
| 12 | Safe fork | Mock-default forks, explicit per-tool live policy, quarantined lineage | Production side-effect qualification; JSON policy editor now implemented |
| 13 | LangGraph / OTel | Sync graph record/replay/fork plus async isolated checkpointer replay; OTLP JSON/protobuf; Phoenix accepted and displayed all seven demo spans; trace-only ingest | Arbitrary existing-checkpoint restoration and real-corpus viewer usability |
| 14 | Hash bisect | Validated O(log N) search after O(N) integrity check | Remote CI gate and real labeled pairs |
| 15 | Sequence alignment | Needleman–Wunsch structured/lexical or local embedding cosine; bounded matrix; aligned dashboard lanes | Real labeled localization accuracy and human review |
| 16 | Taxonomy | Evidence-based categories, raw JSON diagnosis, dashboard comparison | Full proposed taxonomy evaluation / causal attribution not claimed |
| 17 | MCP | Official MCP v1 stdio/Streamable HTTP lifecycle; real local server tests; two-server concurrent capture persisted to SQLite and replayed 50× with process creation forbidden and Python networking guarded | Real fleet coverage; server-initiated callbacks and SDK v2 unsupported |
| 18 | Concurrency | Opt-in async starts/results/errors/cancellations; stored replay; script source/concurrency flags | Arbitrary external scheduling/cancellation timing/threads and real corpus report |
| 19 | Embeddings / neighbors | Actual BGE-small CPU encoding, fingerprinted LanceDB cosine search; synthetic runtime qualified; original-space neighbors in the offline UI; versioned `run-features` export | Human-reviewed neighbor quality on real corpus |
| 20 | Failure map | Offline TF-IDF map plus actual BGE/HDBSCAN/UMAP runtime; cluster/run navigation, keyboard controls and bounded redacted boundary timeline drilldown | Actual Ollama/Qwen evidence-selection contract passes on 15 synthetic runs; deterministic rendering replaces unsupported free prose; real feature relevance and human coherence review remain open |
| 21 | Classifier / eval | Grouped classifier, JSON weights, fixture gate, exact held-out baseline comparison command | Reviewed real labels and held-out prompted-LLM baseline comparison |
| 22 | Real fleet / DSL | Safe boundary-query DSL, weak labels and classifier prediction | 672-tool/10-provider fleet access and hundreds of real runs |
| 23 | Performance / package | Synthetic benchmark, wheel/sdist, console entrypoint; Linux Python 3.11/3.12/3.13 tests and demos | Production budget, PyPI name/credentials/publication |
| 24 | Demo / docs / gallery | Offline recovery demo plus actual local-model capture/live-fork/decision-intervention qualification (200 server-off replays); examples, gallery and strict docs build | Real failing-agent demo and publication of gallery/docs site |
| 25 | Stretch decision | LoRA cut documented; replay safety, compatibility and typing hardened | No model-training claim; retain decision for maintainer review |
| 26 | Release | Published PR candidate, release notes/backlog, digest-checked evidence gate and prepared publishing workflows | Code Owner approval, CI, tag, publish and final real-data Definition of Done |

## Gate sequence to finish the original plan

1. Recheck remote CI on the final PR #43 head and obtain its required independent Code Owner review.
2. Record authorized OpenAI/Anthropic and fleet workloads with credentials configured
   locally. Review redaction before sharing. Run `eval-fixtures` over that corpus.
3. Supply reviewed failure labels grouped by originating task/run; evaluate held-out
   classification against the requested prompted-LLM baseline and human cluster review.
4. Review the qualified model/index and trace-viewer evidence, benchmark real workloads,
   then approve the format ADR and explicitly resolve the partial features above.
5. Deploy docs and publish the reviewed package/tag only after the final acceptance
   checklist passes. Installation from a built wheel is not PyPI publication.

## Engineering contribution

The demonstrated contribution combines deterministic captured evidence, fail-closed
fork exploration, immutable state inspection and evidence-first diagnosis. It is
a coherent implementation contribution; no claim of research priority is made.

## One-pass acceptance and missing inputs

See [completion checklist](completion-checklist.md) for the one-command local
acceptance pass, live-provider capture commands and the external inputs required
for final acceptance. The checklist also names every intentionally unsupported
pattern above; no partial feature is silently promoted to complete.
