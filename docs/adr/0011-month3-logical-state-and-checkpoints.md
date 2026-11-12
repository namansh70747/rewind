# ADR-0011: Logical state, checkpoint adapters and derived snapshot indexes

Status: Implemented

## Context

Month 3 requires schema'd logical state, incremental CAS snapshots, a stable
inspection API, native LangGraph checkpoint/callback evidence and safe forks.
The boundary-log contract frozen in Month 2 must remain readable.

## Decision

- Logical state uses a JSON envelope with exactly `schema`, integer `version`
  and `value`. Schema `rewind.logical-state`, version 1, accepts JSON values and
  declared Pydantic model fields. Non-string mapping keys, opaque Python objects
  and non-finite numbers fail explicitly. There is no executable pickle loader.
- Inspection responses expose `schema_version=1`, the exact boundary and chain,
  observed values, latest explicit agent snapshot, checkpoint/suffix counters
  and final output only at the final boundary. CLI inspection uses persisted
  checkpoints; terminal inspection reuses a single in-memory index.
- The existing snapshot table stores CAS manifests with schema
  `rewind.snapshot-delta`, version 1. A manifest contains a base hash, changed
  response references, source fingerprint, sequence and source chain link.
  Every k checkpoints is a full anchor; intermediate writes contain only changed
  references. Queries apply fewer than k suffix boundaries; delta ancestry is
  also bounded by k. Payload copying still costs O(returned state size).
- Snapshots are derived accelerators. The boundary log is validated when indexing;
  CAS reads check content hashes, and a snapshot's source binding is checked at
  inspection. Cross-run cache substitution fails. Legacy full-map checkpoints
  remain readable. Garbage collection follows base manifests and payload refs.
- Native LangGraph callbacks record logical outputs with stable thread/name
  labels and exclude random framework run IDs. Native checkpoint capture records
  thread values and the next-node frontier. Restoring into a fresh checkpointer
  requires an explicit completed node and checks the resulting frontier before
  continuation. It does not guess opaque scheduling state or restore a Python heap.
- Fork CLI tools are simulated from fresh occurrence-aware recorded fixtures by
  default. Unknown/exhausted fixtures fail closed. Explicit mocks override those
  fixtures; explicit per-tool live manifest entries exclude the automatic fixture
  and authorize that producer. Simulated outcomes remain labeled counterfactual.
- Perfetto exports use complete ordinal slices, not measured wall-time durations.
  OTLP/OpenInference preserve input/output, chain and fork provenance. Trace-only
  imports remain non-replayable.

## Compatibility

No boundary-log fields, chain algorithm or SQLite columns are changed. The new
state/checkpoint/callback kinds use the existing extensible boundary kind field.
Versioned CAS sidecars are derived indexes and can be rebuilt. Existing recordings,
old snapshot maps and the previous CLI demo interface remain supported.

## Validation

`tests/test_month3_gates.py` covers serialization rejection, delta/GC/reopen and
legacy reads, cross-run cache rejection, native checkpoint capture/restore,
callback replay/fork, actual LangGraph fan-out completion ordering, default tool
simulation, explicit live manifests and controlled fork experiments. Real
NVIDIA/Gemini recordings and official Perfetto/Jaeger evidence are listed in
`docs/validation/month3/planner-audit.md`.
