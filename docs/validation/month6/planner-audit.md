# Month 6 planner audit

Scope: weeks 23–26 of the [original six-month plan](../../plan/roadmap-6-months.md#month-6-cooldown-hardening-release-weeks-2326).
The gate IDs below retain their original meanings; explainer/GC tests do not
replace release or performance acceptance.

## Original exit gates

| Gate | Implemented and verified | Remaining acceptance |
|---|---|---|
| M6.1 clean install and tagged release | CI builds wheels; `fr` console script ships | **Course: tag `v0.1.0` on merge.** PyPI publisher still optional. |
| M6.2 acceptable capture overhead | [Measured baseline versus capture](performance.json) on a controlled 12-tool CPU workload; output equality and 50 faithful concurrent replays asserted | Production fleet budget still not claimed. Course accepts the committed measurement. |
| M6.3 newcomer-reproducible killer demo | [Killer demo](../../killer-demo.md) from `fr demo`; NVIDIA/Gemini live path in Month 3 docs; [gallery](../../gallery.md) | Public Pages deploy on `main` via `docs.yml`. |
| M6.4 trained LoRA or documented cut plus hardened core | LoRA is deliberately cut in ADR-0014. Deterministic candidate explanations, strict output verification, shared thread-safe socket guards and GC have regression coverage. No training claim is made. | No model training is required for the documented cut path. |
| M6.5 final Definition of Done | Core tests and interop are exercised in CI; format freeze in ADR-0010/0015 | PyPI and paid OpenAI/Anthropic corpus remain explicitly out of course scope. |

## Correctness fixes

`concurrent_replay` now compares every worker's **final output and fingerprint**
against the recording. Previously it counted any non-raising worker as a pass,
even when the final output was wrong. A regression rejects eight such replays.

Concurrent offline guards share a reference-counted patch lifetime. Each attempt
is attributed through context-local audit state. One thread exiting cannot restore
network functions under another active replay. Explicit live authorization is
context-local and cannot globally unpatch another worker; an explicit nested
replay guard revokes inherited live authorization. Tests exercise controlled
out-of-order guard exits, cross-thread authorization and restoration of originals.
This remains a trusted Python socket guard, not an OS sandbox or a native-I/O guarantee.

Explanations are suggestions, not established causes. Sampling and argument labels
no longer claim proven randomness or hallucination. Known class templates identify
the fields a reviewer should inspect. LoRA training remains deferred.

## Reproduce

```bash
uv sync --frozen --extra dev --extra ml --extra integrations --extra docs --extra tui
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run mkdocs build --strict
uv run python scripts/benchmark_month6.py --output .rewind/month6-new.json
uv run python examples/month6_explainer_gc.py
uv run fr release-check docs/release-evidence/checklist.json
```

The final command is expected to fail until missing release inputs have real,
digest-bound evidence and appropriate review. Do not edit blocked entries to
`passed` merely to obtain a green release. The benchmark records its scenario,
Python/platform, capture/baseline median times and ratio; it does not fabricate
an acceptance threshold. The dedicated Month 6 workflow retains fresh measurements.
