# ADR 0015: Course provider substitution and Month 5–6 close

- Status: Accepted
- Date: 2026-11-18
- Deciders: Aastha, Naman, Kartik (UCS503P)

## Context

The original Month 2 gate asked for unmodified OpenAI and Anthropic agents.
Those APIs are billed. Remaining live work uses **NVIDIA and Gemini only** over
the same `httpx` interceptor. Groq stays as optional extra HTTP evidence, not a
required key. Month 5's 672-tool fleet is not available. Month 6's LoRA stretch
was already cut in ADR-0014.

## Decision

1. Treat NVIDIA and Gemini as the **course equivalent** of the OpenAI/Anthropic
   live-provider gate. The capture plane is still `httpx`; the plan is not rewritten.
2. Freeze the on-disk format described in ADR-0010 as **Accepted** for v0.1.0
   course release: BLAKE3 chains (`b3:`), zstd CAS, portable JSON v2 with
   SHA-256 envelope checksum, legacy BLAKE2b/zlib readable.
3. Close Month 5 on a **substitute local fleet** (≥24 synthetic symptom runs)
   plus a **frozen keyword baseline**, not a paid prompted LLM.
4. Ship Month 6 as tagged **v0.1.0** documentation + killer demo from `fr demo`
   and existing NVIDIA/Gemini evidence. PyPI publication remains optional.

## Consequences

- Faculty can be told Month 2–6 software is complete with documented substitutes.
- We must not claim a signed OpenAI/Anthropic corpus or a 672-tool production
  fleet. Keyword stub provenance must stay in the Month 5 close JSON.

## Alternatives considered

- Wait for paid OpenAI/Anthropic keys — rejected (cost; delays release).
- Fake a prompted-LLM JSON without a model — rejected; the keyword stub is
  explicit and deterministic.
