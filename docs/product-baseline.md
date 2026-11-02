# Product baseline and PR reconciliation

The single-user local product console follows Aastha Tyagi's glass-style visual direction from `feat/week2-mam-timeline-ui` while using the recording, storage and replay core on `main`. Its old seeded demo, local demo credentials, Google login and older server are not ported as product authentication or evidence. The UI reads real local recordings; identified simulated runs are hidden unless selected.

PR #43 is merged on main. The earlier PRs #30 (live-demo runner), #31 (provider/retry implementation), and #40 (Aastha's demonstration UI) have overlapping changes and merge conflicts against main, including core recording/store/CLI files. PR #36 targets the old #30 feature branch. Their behavioral intent must be reconciled against the current implementation and reviewed independently; none is blindly merged or closed. Dependency PRs are unrelated to the product feature and require their own compatibility checks.

The free-provider milestone remains unqualified until live NVIDIA and Gemini captures and offline replays are recorded with fresh credentials. This milestone is distinct from the original OpenAI/Anthropic gate. Current product checks do not establish a frozen recording format, universal I/O interception, or production security isolation.
