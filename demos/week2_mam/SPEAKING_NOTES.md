# Month-1 Demo Console — Speaking Notes (~6 minutes)

**Launch:** `.\demos\week2_mam\run.ps1` → http://127.0.0.1:8765/

**Login first:** Continue with Google, or Create account (email + 8-character password), then Sign in.

---

## Opening
After sign-in, Month 1 is complete (M0 + M1). Replay is playback of recorded boundaries, not model re-execution (ADR-0006). Top strip shows COMPLETE and 100/100 PASS.

## Results 100×
Correct run verified bit-exact offline with kill-switch on. Optional: re-run verify to show live engine proof (progress every 10 replays).

## Try it live
Live capture tab → city Mumbai → Run agent + verify (Open-Meteo weather, then offline verify).

## Correct run → Bug case → Find the bug
Correct advice vs intentional wrong advice. Bisect stops at boundary #2 — same weather input, different LLM output.

## Capture & store / Spikes / Corpus
SQLite + CAS blobs, spikes A–F PASS, corpus faithfulness 100%.

## Close
Same surface as CLI: `fr record -- python` / `show` / `verify` / `bisect`. Plan: `docs/plan/month1-status.md`.
