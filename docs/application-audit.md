# Rewind application audit runbook

Use a clean wheel installation, a disposable workspace and a separate SQLite
database. Keep provider credentials outside the workspace used for local checks.
Record the commit, wheel hash, Python version, OS and run IDs alongside results.

## Acceptance sequence

| Layer | Procedure | Pass condition |
|---|---|---|
| Regression | Run pytest, Ruff, mypy and strict MkDocs. | All mandatory checks pass. Record every skip or failure. |
| Installed alpha | In Chrome, open the loopback workspace, capture actual local inference, inspect recorded boundaries and verify 50 replays. Visit Compare, Providers and Settings. | Correct output against an external oracle, one fingerprint, accurate provider and job states. |
| Failure and fork | Record a real model response truncated by a deliberately small token cap. Compare it with a healthy run and fork using a known recorded response. | Detect input drift, preserve the parent, check child output independently. Label the fault and replayed response in evidence. |
| Load and controls | Run the workspace script below against the isolated server. | Zero errors and stable output. Report latency percentiles and throughput; record all control checks. |
| Performance | Run the paired capture benchmark. Add target-fleet p95 and resource measurements before release. | Identical output and reproducible measurements within the agreed target-workload budget. |
| Recovery | Restore a SQLite live backup into a disposable location and verify integrity and the saved run. Follow up with restart, interrupted worker, full-disk and rollback matrix checks. | Original database remains intact. Restored run has identical fingerprint and output. |
| Independent beta | Have external developers install from the docs and submit structured feedback on capture, compare, replay and fork. | At least two independent walkthroughs and resolution/retest of primary-flow blockers. |

```bash
uv run python scripts/audit_workspace.py --port 18767 --db /path/to/audit.db \
  --run YOUR_RUN_ID --requests 600 --workers 16 --output /tmp/workspace-audit.json
uv run python scripts/benchmark_month6.py --samples 40 --output /tmp/capture-performance.json
```

The stress script measures concurrent reads of one recorded payload on loopback.
Measurements cover that payload, machine and concurrency level. The security
checks verify framing and connection directives and mutation authentication.
The native recorder still runs trusted Python code. Track CSP hardening, export
privacy, trust-boundary review and OS isolation in separate release checks.

See the [Mac audit results](release-evidence/local-application-audit.md) for the recorded baseline.
