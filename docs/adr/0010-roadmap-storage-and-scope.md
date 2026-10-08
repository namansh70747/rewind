# ADR 0010: storage evolution and release scope

Status: proposed; not merged or frozen. Date: 2026-10-08.

New cassettes use BLAKE3 boundary chains. CAS identifiers are prefixed `b3:` and
payloads use zstd; bare legacy digests remain BLAKE2b/zlib. Stored metadata records
the chain algorithm. Portable JSON v2 carries that discriminator and a SHA-256
envelope checksum; v1 imports use the legacy algorithm. Integrity is checked before
use. This provides corruption detection, not signatures or hostile-rewrite protection.
Snapshot references participate in mark/sweep GC.

The format remains proposed until reviewed compatibility fixtures and maintainer
approval satisfy the roadmap's freeze gate. Avoid treating 0.1.0 metadata as a
published release or stable protocol contract.

Week 25 decision: cut LoRA. No reviewed training corpus, qualified generative explainer model or
CPU/GPU comparison is available. The qualified BGE encoder is not a generative LoRA explainer. Spend the remaining effort on fail-loud replay,
backward-compatible storage, safe forks and executable documentation. This follows
the roadmap's explicit scope-cut option and does not imply the ML gates passed.
