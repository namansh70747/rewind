# Month 6 planner audit

Scope: weeks 23–26 of the [original six-month plan](../../plan/roadmap-6-months.md#month-6-cooldown-hardening-release-weeks-2326).
The gate IDs below retain their original meanings; explainer/GC tests do not
replace release or performance acceptance.

## Original exit gates

| Gate | Implemented and verified | Remaining acceptance |
|---|---|---|
| M6.1 clean install and tagged release | CI builds wheels on Linux/macOS/Windows, installs into clean environments, and exercises the CLI/demo; CHANGELOG and publishing workflow exist | No `v0.1.0` tag/release or verified PyPI publisher ownership is recorded. `release-check` intentionally blocks publication while evidence is missing. |
| M6.2 acceptable capture overhead | [Measured baseline versus capture](performance.json) on a controlled 12-tool CPU workload; output equality and 50 faithful concurrent replays asserted | Target-fleet measurement and an agreed production overhead budget. A synthetic number is not production acceptance. |
| M6.3 newcomer-reproducible killer demo | [Month 3 workflow](../../month3-time-travel.md) documents record/replay/fork using actual NVIDIA/Gemini examples; committed actual-provider reports show zero mutating fork calls. The portable viewer/browser and examples run in CI. | Final newcomer walkthrough, public docs/gallery validation, and final release evidence review. Reusing earlier provider evidence is not a fresh provider call. |
| M6.4 trained LoRA or documented cut plus hardened core | LoRA is deliberately cut in ADR-0014. Deterministic candidate explanations, strict output verification, shared thread-safe socket guards and GC have regression coverage. No training claim is made. | No model training is required for the documented cut path. |
| M6.5 final Definition of Done | Core tests and interop are exercised in CI; the release manifest fails closed on missing evidence | Release checklist still requires real fleet/labels, reviewer attestations and publisher setup. Merging software does not silently waive these. |

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
