# Week 2 Mam Demo — Speaking Notes (~4 minutes)

**Launch:** `.\demos\week2_mam\run.ps1`  
**URL:** http://127.0.0.1:8765/  
**Needs:** no API key (offline fixtures)

---

## Opening (20 sec)

> “Ma’am, Rewind is a flight recorder for AI agents.  
> Week 1–2 we proved: record a run, replay it bit-exact offline, and find where two runs first diverge.  
> This UI is the same engine as our CLI — so you can *see* the failure.”

---

## Act 1 — Good run

Click **1 · Good run**.

> “This agent geocodes Mumbai, fetches weather (27.8C, precip 0), then asks an LLM for umbrella advice.  
> Every row is one HTTP boundary we captured.”

Click boundary #2 (LLM).

> “Clear advice: leave the umbrella. That matches the weather.”

---

## Act 2 — Failed run

Click **2 · Failed run**.

> “Same task, same weather inputs — but in production the model gave wrong advice: heavy rain / take an umbrella while precip was 0.  
> That is the failure we need to localize.”

Click the red-tinted step (#2).

---

## Act 3 — Find failure

Click **3 · Find failure**.

> “Auto-bisect walks both recordings and stops at the first difference.  
> Boundary #2: **same input → different output** — the LLM decision diverged here.  
> Geocode and weather matched; only the model answer changed. That is the failure point.”

---

## Act 4 — Proof

Click **4 · Proof**.

> “We replayed the good run **100 times** offline with the network kill-switch on.  
> BIT-EXACT 100/100 — same fingerprint every time, zero API calls.”

Optional: click **Re-run verify 100×** (takes ~1–2 min) to show live proof.

> “Terminal commands `fr show`, `fr verify`, `fr bisect` do the same work; this UI is for the demo surface.”

---

## If she asks “is this hardcoded?”

> “The HTTP answers are fixture transports so the room needs no API key.  
> Capture, hash-chain, verify, and bisect are the real `flightrecorder` library — same as CI.”

---

## Backup (terminal)

```powershell
cd C:\Users\vt903\Projects\rewind
$env:PYTHONPATH="src"
python demos/week2_mam/seed.py 100
python -m pytest tests/test_week2_mam_demo.py -v
```
