# ADR-0012: validated bisect and MCP fleet evidence

Status: accepted implementation; human interpretation acceptance remains separate.

## Decision

Use one diagnosis implementation for CLI, portable HTML and product comparison.
Validate both complete hash chains before any diagnosis. For aligned runs, locate
the first unequal chain link with binary search; expose the comparison count.
This is O(log N) hash comparisons after O(N) validation, not an O(log N) end-to-end
report. The raw report and first logical decision can require a linear scan.

Use bounded global Needleman–Wunsch alignment for shifted sequences, anchoring the
identical observed prefix. Response values do not influence suffix substitution
costs: otherwise a changed output could be hidden as an insertion/deletion. Costs
combine recursive structured arguments and actual cosine embeddings when supplied;
lexical fallback is explicitly labeled. The grid has a one-million-cell budget.
The custom implementation keeps index/gap semantics and the cap explicit without
adding Biopython/RapidFuzz runtime dependencies suggested by the plan. This is an
implementation substitution, not a claim those libraries were used. Smith–Waterman
is unnecessary because dropping unmatched run ends would hide divergence evidence.

Repeated identical calls have ambiguous occurrence identity; deterministic prefix
anchoring/tie-breaking cannot infer unobserved causal correspondence. Auto hash
mode requires a compatible shape with identical input sequences or unique keys;
explicit hash mode is a caller assertion of positional alignment. Cached vectors
select alignment in auto mode. Reject corrupted or oversized comparisons rather
than silently degrading to positional answers.

Separate raw metadata/source mismatches from decision differences. Normalize only
known provider transport metadata and MCP SDK occurrence/RPC identifiers for
logical matching. Preserve full raw events and JSON-pointer diffs. Weak taxonomy
labels never establish causality; require human agreement on a real pair for M4.2.

Embedding calls are explicit, NVIDIA-only cloud operations with source-bound vector
caches; ordinary replay and diagnosis stay offline. Private recording disclosure
is distinct from API-key authorization. Validate the live API with public synthetic
inputs; do not treat that as live production root-cause validation.

Observe public MCP SDK object streams instead of patching internal protocol state.
Associate client request IDs with an operation through a context-local owner and
match responses per session. Store redacted JSON-RPC frames with the normalized SDK
outcome. Preserve backwards replay of recordings without frames. Fleet lifecycle
and tool operations sit behind the same adapter for stdio and streamable HTTP.
Ignore notifications/server-initiated requests for this version's call contract.
A recording proves the captured calls on tested servers, not every MCP feature.

Persist opt-in concurrent mode through generic record/verify. Reuse the existing
start/terminal schedule recorder, with bounded mismatch waits and explicit
error/cancel events. Extend trusted-script provenance to Git identity and loaded
local Python files; source content governs replay, not Git SHA equality alone.

## Consequences and evidence

Sequence alignment is quadratic in suffix lengths and embedding dimension, capped
before allocation. Semantic caches can expose private information despite lacking
text. MCP replay guarantees logical response/completion fidelity, not transport
packet timing. Root-cause labels require task context and review.

See [the Month 4 audit](../validation/month4/planner-audit.md) and
[usage and guarantees](../month4-bisect-fleet.md).
