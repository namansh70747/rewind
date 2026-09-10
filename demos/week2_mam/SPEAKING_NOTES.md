# Weeks 1–4 Mam Demo — Speaking Notes (~5 minutes)

**Launch:** `.\demos\week2_mam\run.ps1`  
**URL:** http://127.0.0.1:8765/  
**Plan:** `docs/plan/roadmap-6-months.md` Weeks 1–4 (M1 walking skeleton)

---

## Opening

> “Ma’am, this is Rewind — a flight recorder for AI agents.  
> Per our plan, Weeks 1–4 build the walking skeleton: prove bit-exact playback, fail loud, capture to store, then verify with a kill-switch.  
> The UI shows that thread on a real agent example.”

Point at the four **Week** cards (PASS evidence is live from the engine).

---

## Good run

> “Agent: Mumbai → weather → LLM umbrella advice. Each row is one captured HTTP boundary.”

---

## Failed run

> “Same weather (precip 0), but the model gave wrong advice — take an umbrella for heavy rain. That is the production failure.”

---

## Capture & store (Week 3)

> “Recording is persisted in SQLite with content-addressed blobs. Dedup held when we re-saved the same payloads.”

---

## First failure (bisect)

> “Auto-bisect stops at boundary #2: same input, different output — the LLM decision. Geocode and weather matched.”

---

## Verify 100× (Week 4 / M1)

> “Good run replayed 100 times offline, kill-switch on, one fingerprint. Tamper oracle fails loud at boundary #2.  
> Same work as `fr show` / `fr verify` / `fr bisect`.”

---

## Backup

```powershell
$env:PYTHONPATH="src"
python demos/week2_mam/seed.py 100
python -m pytest tests/test_week2_mam_demo.py -v
```
