# Rewind user-journey audit

## Release decision

**Local developer alpha passed for the exercised journeys. Public deployment and external beta remain open.** An installed copy of Rewind on macOS captured a real Git and Ollama workflow through Chrome, displayed the evidence, and verified it 50 times. The browser application executes trusted scripts with the local operator's permissions and stores recordings on that machine. A public multi-user service needs a separate execution and storage design.

Scope was the actual installed application, its CLI, the browser and the local workspace API. This audit used neither unit tests nor hosted-provider calls. Stress data and deliberately triggered failures were confined to disposable workspaces. See the [previous application audit](local-application-audit.md).

## What a user can do today

| Screen or path | User scenario and observed result |
|---|---|
| Overview and first entry | Clean install showed zero recordings. **Start your first capture** opened Capture via Enter. Restored Overview showed four recordings and their existing verification state. |
| Capture | Unchecked trust was rejected with an actionable error. Changing scripts now clears prior consent. A deliberately slow capture could be cancelled, a deliberately failing script produced a failed job, and a real capture succeeded afterward. |
| Recordings | Opened capture `30406a1288be`. Timeline showed the actual Git tool call and Ollama HTTP response, including the request, response and chain fingerprint. The CLI independently showed the recorded output matching the actual checkout commit. |
| Export and import | Export showed a download request. The application export endpoint returned a 2,534-byte portable bundle without a trusted source reference. Chrome's download completion was not confirmed. Enter on **Import bundle** opened the file picker. A malformed JSON import produced an error. Importing the app's exported bundle succeeded afterward and showed an inspection-only state. |
| Verification | The clean workspace began with Start verification disabled. The captured script completed **50/50** offline replays with one output and one fingerprint. The imported copy was not offered for execution. The restored workspace preserved the earlier 50× result. |
| Compare | Compared healthy `bbf27a05235d` with token-limited `ffd0029719e0`. The UI showed request drift at boundary 1 and displayed both raw packets when the alignment row was activated by keyboard. The token limit was deliberately induced for audit. |
| Fork | The browser now labels `c93c4c635a50` as a fork and displays its parent fingerprint and edited boundary. This existing fork substituted a recorded healthy response through CLI. Its Git revision matched the real tool result. Creating a fork is a CLI step. |
| Providers | Groq, Gemini, NVIDIA and xAI were visible with absent credentials and disabled checks. Real inference used local Ollama. Account reachability, model capability, quota and retry behavior are still open for the four hosted providers. |
| Settings and privacy | The restored workspace's audit scanned four recordings and nine blobs, with zero known-pattern matches, integrity failures, unreadable blobs or invalid stream objects. The UI describes the scan scope and trusted local execution. |
| Recovery | Chrome showed cancelled and failed jobs distinctly. A successful capture followed both. A SQLite backup opened in a separate installed server and kept four recordings, lineage and the prior verification state. Full disk, abrupt host loss, and descendant-process cleanup remain unqualified. |

## Stress and performance

The 140-recording library had 96 boundaries per run, for 13,440 boundaries total. The same macOS ARM host and SQLite data were used on both builds. Each measured list request retrieved and decoded all 140 summaries over loopback. p95 uses nearest rank. Capacity figures apply to listing that library on this machine.

| Load profile | Previous p50 | Previous p95 | Candidate p50 | Candidate p95 | Candidate errors |
|---|---:|---:|---:|---:|---:|
| 24 requests, one worker | 419.6 ms | 456.4 ms | 2.90 ms | 8.58 ms | 0 |
| 24 requests, six workers | 10,545.8 ms | 11,838.8 ms | 39.93 ms | 45.04 ms | 0 |
| 600 requests, 16 workers | — | — | 175.24 ms | 226.07 ms | 0 |

The previous list decoded all recordings and performed one verification lookup per item. The candidate reads summaries, metadata and verification status in one query. Opening a recording still loads and validates its boundaries. The 600-request run took 6.44 seconds. The benchmark does not cover concurrent capture, long sessions, browser rendering with thousands of rows, or a shared hosted service. The maximum at 16 workers was 285.48 ms.

## Release gates still open

| Priority | Gap | Evidence required to close |
|---|---|---|
| Launch blocker for public hosting | Trusted OS-level execution, loopback-only server and single workspace | Choose distribution model. For hosted execution, prove per-tenant authorization and recording isolation, isolated workers with minimal mounts and scoped network and credentials, plus resource and cancellation limits. Verify on staging with a dedicated test tenant. |
| Before supported local beta | Independent first-use evidence | Have external developers on clean installs complete capture, replay, compare and portability using only docs. Record completion, time, where help was needed, and retest recurring failures. Add Safari, Windows/Linux, responsive and screen-reader evidence. |
| Before claiming provider coverage | Four cloud accounts and workloads | Run real per-provider capture/replay on rotated credentials with approved spend. Exercise streaming, retries, timeouts, quota and actual tools. Confirm provider calls independently during capture and zero traffic on replay. |
| Before making reliability claims | Mixed-load and recovery evidence | Record while other users of the same local workspace inspect, compare and export. Measure detail and list latency, memory and disk growth, and long-run soak. Exercise interruption, database contention and loss of disk space on a disposable copy. Verify rollback and recovery with persisted run counts and fingerprints. |
| Before claiming full browser recovery | Download completion and keyboard flow polish | Confirm the downloaded file appears in Chrome and round-trips on a second machine. Provide actionable, consistent errors for malformed data, source drift and unsupported recordings. Add a browser fork flow backed by the existing CLI policy. |
| Before claiming advanced diagnosis | Real corpus and interoperability | Qualify TUI and Perfetto/OTel in their actual viewers, real MCP/LangGraph workloads, and the 200-run fleet gate with independent human labels and documented model evidence. |

## Reproduction references

- Baseline workspace build `1baa621`, candidate based on `b4bbce8`. macOS 26.6.2 ARM64 with a new Python 3.13.7 venv. Candidate dependencies were resolved for the installed wheel.
- Main benchmark wheel SHA-256 `394b7d758393a1c868e31a0f8b7991c34d7347699a5dcf978e6e391683e0afbc`. Follow-up wheel for consent, keyboard import and cancellation copy `90fb11448d2e821e1e9bde018481cdee83e0f3cdfcc61588d0529981a7f1ca13`. Both have the same list query.
- Run `fr serve --workspace . --db workspace.db --port 18769` from the disposable workspace. In Chrome, follow Overview → Capture → Verification → Recordings. Use `fr show` to compare the recorded result to the real project's `git rev-parse HEAD`. Use packages and artifacts scoped to local test workspaces.
