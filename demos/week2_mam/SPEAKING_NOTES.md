# Month-1 Mam Console — Speaking Notes (~6 minutes)

**Launch:** `.\demos\week2_mam\run.ps1` → http://127.0.0.1:8765/  
**Plan status:** `docs/plan/month1-status.md` (M0 + M1 COMPLETE)

---

## Opening

> “Ma’am — this is Month 1 of the Rewind plan: prove bit-exact playback, fail loud, capture to store, verify with a kill-switch.  
> The gate cards are live engine results, not slides.”

Point at **M0 / M1 / COMPLETE**.

---

## Live agent

> “Record live run — Open-Meteo weather is real HTTP. We capture three boundaries, then verify offline with the network kill-switch.”

Optional: set `NVIDIA_API_KEY` for a live LLM; otherwise stub LLM + live weather.

---

## Good → Failed → First failure

> “Same weather (precip 0). Failed run invents heavy rain. Bisect stops at boundary #2 — same input, different output.”

---

## Spikes + Corpus

> “Spikes A–F are the Week-2 go/no-go pack. Corpus is twelve city fixtures at 100% faithfulness.”

---

## Verify 100×

> “Good run replayed 100 times, one fingerprint. Tamper fails loud. Same as `fr show` / `fr verify` / `fr bisect`.”

---

## Backup CLI

```powershell
$env:PYTHONPATH="src"
python -m flightrecorder.cli record -- python demos/week2_mam/agent.py Mumbai
python -m pytest tests/test_week2_mam_demo.py tests/test_walking_skeleton.py -q
```
