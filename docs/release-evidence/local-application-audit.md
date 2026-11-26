# Rewind application audit

The installed wheel at commit `1baa621` ran on an Apple Silicon Mac using Python
3.13.7. Chrome used the real loopback application and an isolated database.
Ollama ran `qwen2.5:0.5b`. The independent application check compared the model's
answer with the exact Git revision.

| Area | Result | Observed evidence |
|---|---|---|
| Hands-on alpha | Passed for exercised flow | Chrome opened the clean workspace, captured real Git and Ollama boundaries, inspected the timeline and verified 50 replays. The provider settings showed all four configured provider choices with keys absent from the audit process. |
| Comparison | Passed | Chrome compared an identical recording and showed no divergence. CLI compared the healthy capture with a real, deliberately token-limited inference and located input drift at boundary #1. |
| Failure replay | 50/50 | Token-limited run `ffd0029719e0` reproduced the truncated output. |
| Counterfactual | Passed for this case | Fork `c93c4c635a50` substituted a previously recorded healthy response. The exact Git hash check passed and the parent fingerprint stayed intact. The original failure was induced by the audit and the fork used playback. |
| Loopback stress | 600/600 reads | 16 workers, 0 errors, 839.41 requests/s, p50 15.798 ms, p95 44.102 ms. One small recording on this Mac. |
| Capture performance | +1.77% median | 40 pairs on a controlled 12-tool CPU workload. 8.615 ms baseline, 8.767 ms captured. 50/50 concurrent replays. |
| Backup recovery | Passed | SQLite online backup opened from a separate location, integrity check passed, fingerprint and output matched. |
| Defensive controls | 3/3 checks | Framing blocked, browser connections restricted to same origin, mutation without a token rejected. In-app corpus audit scanned one recording and four blobs with zero known-pattern matches. |
| Regression | 217 passed | The Python suite covers additional provider transport, portability, streaming and MCP behavior. These checks are separate from the manual app journey. |

The Chrome Settings screen contained stale wording about old provider gates.
The audit follow-up updates that wording and adds the repeatable local audit
runner. The audited wheel predated this wording fix.

## Open acceptance

- Repeat with independent beta participants and retain their unassisted task
  completion, timings and feedback. Internal Chrome testing is alpha evidence.
- Run hosted model qualification after credential rotation and approval of
  per-provider limits. This audit used real local inference and made no hosted
  model calls.
- Qualify a naturally observed application failure with real LangGraph/MCP
  continuation and separately validate the authorized production fleet.
- Measure mixed load with large runs and writing jobs. Extend recovery with
  interruption/restart, full-disk and rollback tests. Cover cross-platform
  installation, accessibility and the full visual/browser suite.
- Continue privacy and sandbox qualification. The loopback server runs trusted
  scripts with local privileges. A known-pattern scan has limited coverage.
