# ADR 0015: Proposed course evaluation substitutes

- Status: Proposed; course and maintainer approval pending.
- Date: 2026-11-18; evidence-integrity corrections 2026-11-26.

## Proposal

Evaluate NVIDIA/Gemini capture separately from the original OpenAI/Anthropic
SDK corpus. Use 24–30 synthetic symptom recordings to exercise Month 5 tooling
and compare a classifier against an unmodified keyword heuristic offline.
A prompted-model baseline is available only with explicit live opt-in.

## Limits

These checks do not satisfy the original 672-tool production-fleet requirement,
independent human-review requirement, or prompted-LLM comparison. The keyword
heuristic may tie or beat the classifier; report the measured outcome unchanged.
No course reviewer approval is asserted by a program-generated report.

ADR-0010 format approval, real-workload budgets, tagged release, public docs
and the original release checklist remain separate requirements. LoRA remains
cut under ADR-0014. Merging this proposal does not approve or publish a release.
