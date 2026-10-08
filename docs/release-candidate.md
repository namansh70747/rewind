# Release candidate notes and retrospective

Unpublished local 0.1.0 candidate. The GitHub main branch is not this candidate.

Added BLAKE3/zstd with legacy readers, selected nondeterministic-source capture,
decorated tools, recorded HTTP failures, async completion ordering, immutable
checkpoints, policy-controlled forks, script forks and fixture evaluation.
Added terminal inspection, trace interoperability, structured alignment, MCP exchange
and LangGraph adapters, safe queries, offline fleet maps and grouped classification.

What worked: preserve a keyless reproducible demo; retain raw evidence alongside
interpretations; test intercepted effects rather than claim whole-process replay;
keep model artifacts as inspectable JSON.

What remains uncertain: production SDK/fleet diversity, real-world redaction recall,
external viewer acceptance, real-fleet embedding usefulness, actual capture budget and
classifier usefulness. Local controlled tests cannot settle these questions.

Backlog: MCP server-initiated callbacks and SDK v2; arbitrary external cancellation timing; richer binary
HTTP fidelity; dependency provenance; async LangGraph checkpoint qualification;
real labeled semantic alignment accuracy; real fleet benchmarks; hosted sharing;
publication of the prepared synthetic gallery; release automation and Windows/macOS evidence.

Release procedure: review the evidence ledger, resolve required gates, submit PR,
obtain Code Owner approval and green CI, build reproducibly, smoke-test the wheel,
publish using maintainer credentials, then tag and publish release notes.
