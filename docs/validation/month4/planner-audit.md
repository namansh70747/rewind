# Month 4 planner audit

Implementation scope: weeks 14–18 in the repository's
[original planner](../../plan/roadmap-6-months.md#month-4-auto-bisect-fleet-capture-weeks-1418).
This branch stacks on the unmerged Month 3 PR; neither branch is merged by this work.

## Week-by-week evidence

| Week / owner | Delivered work | Verification |
|---|---|---|
| 14 / E1 | Validated hash-chain binary search, exposed counts and raw chain evidence | Injected result at every one of 64 steps; boundary cases at 0/1/128/256 of 257; corrupted chain rejected |
| 14 / E2 | `fr bisect` uses unified diagnosis; plain-English and JSON modes, explicit method, deterministic exit codes | CLI regression with identical and failing pairs |
| 14 / E3 | Independent declared edit positions and labels in `examples/month4_pairs.py` | 77 controlled cases, 77 correct localization/category predictions |
| 15 / E1/E3 | Prefix-anchored bounded Needleman–Wunsch, structured JSON similarity and real cosine-vector cost, explicit NVIDIA vector capture/cache | Insert/delete/repeat tests, semantic-vector choice test, cache binding/reversal/rejection tests, live synthetic NVIDIA embedding check |
| 15 / E2 | Portable and product side-by-side aligned timelines with gaps, row selection and correct inspector index | Native Chromium acceptance passed in GitHub CI; aligned gaps, keyboard selection, inspector jump and responsive layout verified |
| 16 / E3 | Eight planned taxonomy labels plus metadata/source/final-output distinctions | Controlled taxonomy cases and actual provider pair reports; these are weak labels, not production cause accuracy |
| 16 / E2 | Plain English with both full raw sides; direction-specific re-diagnosis when swapping portable comparisons | Raw field assertions and reversed cost-label regression; UI acceptance script |
| 16 / E1 | `input_relation`, earliest raw mismatch vs first logical decision, upstream row context | UUID-before-tool and provider-metadata-only regression cases |
| 17 / E1/E2 | MCP SDK public-stream JSON-RPC observation and lifecycle registry; stdio and streamable HTTP | Actual local servers, `tools/call` frames and matching request/response IDs; tool error capture |
| 17 / E3 | Multi-server concurrent corpus generator and portable fleet recording | Two transports, two servers, three tool calls, 50 offline replays; corpus generated privately, metadata report committed |
| 18 / E1 | Persist concurrent mode through generic APIs, recorded completion order and bounded mismatch failure | gather/as_completed completion tests, async error/cancel replay, incomplete fan-out timeout, actual fleet replay |
| 18 / E2 | Stable bisect/embedding/HTML commands; script Git SHA plus main/imported-local source hashes | CLI tests, imported helper drift fails before execution with recorded/replaying SHA diagnostics |
| 18 / E3 | Accuracy/faithfulness report, real pair review and explicit acceptance statuses | Reports linked below; M4.2 agreement recorded in human-review.json |

The planner lists Biopython/RapidFuzz as possible alignment libraries. This
implementation uses a bounded custom global aligner and recursive structured
similarity instead; [ADR-0012](../../adr/0012-month4-bisect-and-fleet.md) records the
choice. No unapproved scope is silently dropped.

## Measured results and limits

- [Controlled accuracy and actual fleet report](accuracy-and-fleet.json): **77/77**
  declared synthetic edits localized and weakly categorized. This includes 64
  aligned response flips, insertion, deletion, repeat, tool choice, argument,
  retrieval, sampling, truncation, cost, UUID noise, and final-output-only drift.
  This is regression accuracy, not a held-out estimate of production root causes.
- Actual mixed fleet: stdio + streamable HTTP, two independently running servers,
  three `tools/call` operations including an error, **50/50** matching replays,
  zero replay network/process launches or repeated marker effects. Original
  server processes were stopped; replay runs under the socket guard and forbidden
  process-launch hooks. SDK-generated `tools/list` pairs are preserved too.
- [NVIDIA synthetic embedding check](nvidia-synthetic-embeddings.json): an actual
  NVIDIA embedding request succeeded on public hand-authored fixture inputs,
  with finite source-bound vectors used by the aligner. No private recording
  inputs were sent in this validation. Offline tests also verify that changing
  supplied cosine vectors changes an ambiguous repeated-tool alignment.
- [NVIDIA actual pair](nvidia-real-pair.json) and
  [Gemini actual pair](gemini-real-pair.json): existing actual model recordings
  from Month 3, not new cloud generations. Each parent/fork pair differs first
  at quote step 1: same input, 420 passing vs 720 failing, budget 500. The named
  observation is **tool-result-drift** before the model continuation. Quote tools
  are controlled fixtures, not production market data. Comparisons ran offline;
  full recordings/prompts and vector caches are not committed.

Local full-suite/type/lint results and CI results are listed in the PR. The
browser script checks aligned insertion/deletion, reversing baseline/candidate,
keyboard selection, inspector jump, desktop/mobile width, literal script-breakout
content, zero portable network requests, and product raw panes. The local sandbox
rejects Chromium's Unix socket; outside-sandbox execution is unavailable by policy.
CI supplied the independent browser execution environment. The
[Month 4 acceptance run](https://github.com/namansh70747/rewind/actions/runs/43330409517)
passed the real mixed-transport fleet and every browser assertion, with zero
runtime errors. Its [artifact](https://github.com/namansh70747/rewind/actions/runs/43330409517/artifacts/13994572581)
contains desktop/mobile screenshots, portable synthetic HTML and reports.

The [remote-check snapshot](github-checks.json) records both published source
commits and their checks. Python 3.11/3.12/3.13, lint/types, strict docs, clean wheels
on Linux/macOS/Windows, CodeQL, Month 3 viewer acceptance, and Month 4 acceptance
all passed. Provider-key CI jobs were opt-in skips; actual session API evidence
is reported separately above. Both PRs remain open and unmerged.

## Exit gates

| Gate | Status | Evidence / remaining action |
|---|---|---|
| M4.1 first diverging decision, aligned and insert/delete | Automated implementation and regression checks complete | Validated hash search, bounded semantic alignment, 77 controlled cases, both actual provider pairs |
| M4.2 named cause, raw diff, human agreement on a real pair | **PASS — human agreement recorded** | Repository owner agreed on 2026-11-13; see human-review.json |
| M4.3 actual multi-server MCP bit-exact replay | Automated acceptance complete | Real mixed transports, matching protocol frames, 50 replays and zero repeated effects |
| M4.4 documented concurrent-tool replay guarantees | Automated acceptance complete | Completion/error/cancel/mismatch tests, persisted concurrent mode, real fleet replay |

### Human review packet (M4.2)

Both actual Gemini/NVIDIA pairs show the same reviewable facts:

| Field | Passing recording | Failing recording |
|---|---|---|
| First differing logical decision | `month3.quote`, boundary 1 | `month3.quote`, boundary 1 |
| Recorded tool input | identical | identical |
| Returned price | 420 | 720 |
| Budget | 500 | 500 |
| Proposed named observation | Tool result changed before the model continuation | `tool-result-drift` |

Question for the reviewer: **Does “the same tool input returned a different result”
correctly name this first difference?** The proposed label describes the observed
change, not why a real external service would change its result. The repository owner, Naman Sharma, responded **“yes i agree”** in this chat on
**2026-11-13**, after the observed tool-result drift was explained. The
[review record](human-review.json) preserves the response and exact scope. This
is assisted review of the displayed evidence, not an independent blind review
or proof of an external root cause. With this agreement, all four Month 4 exit
gates are satisfied within the documented guarantees. Both PRs remain unmerged.

Automatic approval review rejected the optional export of private recording inputs
to NVIDIA embeddings: key use did not by itself authorize disclosure of recording
contents. That export remains blocked. It is unnecessary for the offline real-pair
review or the separately verified synthetic embedding path. If private semantic
validation is desired, explicitly approve that disclosure first.

## Reproduction and CI

See [commands and guarantees](../../month4-bisect-fleet.md). The new Month 4
acceptance workflow runs the controlled oracle, actual mixed-transport fleet and
native Chromium browser checks without provider keys. Live synthetic embeddings
are a separate opt-in job using the repository NVIDIA secret; skipped live jobs
are not fresh API evidence. Existing CI, Month 3 acceptance, docs and CodeQL filters
include the stacked Month 3 base branch, so a stacked PR receives the same checks.
