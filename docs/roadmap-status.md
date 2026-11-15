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
| 19 | Embeddings / neighbors | Actual BGE-small CPU encoding, fingerprinted LanceDB cosine search; synthetic runtime qualified; original-space neighbors in the offline UI; versioned `run-features` export. Event-feature `fr similar` neighbors stay inside failure family | Verified in `docs/validation/month5/neighbor-and-cluster-review.json` |
| 20 | Failure map | Offline TF-IDF map plus actual BGE/HDBSCAN/UMAP runtime; cluster/run navigation, keyboard controls and bounded redacted boundary timeline drilldown. Synthetic three-family HDBSCAN purity is 100% | Human agreement recorded in `docs/validation/month5/neighbor-and-cluster-review.json` |
| 21 | Classifier / eval | Grouped classifier, JSON weights, fixture gate, exact held-out baseline comparison command. Classifier beats majority-class and prompted-LLM baselines | Evaluated in `docs/validation/month5/baseline-comparison.json` |
| 22 | Real fleet / DSL | Safe boundary-query DSL, including `every tool error`, `every retry` and `first context > N tokens`; `fr match` reports a neighbor cluster and weak cause | MCP fleet matching verified in `docs/validation/month5/mcp-fleet-matching.json` |
| 23 | Performance / package | Concurrent replay (`month6.concurrent_replay`), structured `rewind.benchmark.v1` evidence record, `fr benchmark-replay` command. Throughput > 2,800 replays/s | Approved performance budget in `docs/release-evidence/performance-budget.json` |
| 24 | Demo / docs / gallery | Offline recovery demo plus local model intervention; `fr explain` returns deterministic plain-English narration; `fr gc` manages retention; verified sample gallery | Validated in `docs/release-evidence/recovery-demo-qualification.json` and `docs/gallery.md` |
| 25 | Stretch decision / hardening | LoRA cut documented in ADR-0014, `lora_status` field in `rewind.explain.v1`, replay safety and typing hardened | Documented in `docs/adr/0014-month6-lora-explainer-stub.md` and `docs/release-evidence/spike-decision-qualification.json` |
| 26 | Release | Published PR candidate on `feat/month-6-lora-explainer`; all 13 gates pass `fr release-check docs/release-evidence/checklist.json`; PyPI release workflow prepared | Code Owner review and all 13 gates attested in `docs/release-evidence/checklist.json` |

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
