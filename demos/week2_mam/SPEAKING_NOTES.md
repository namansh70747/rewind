# Month-1 Mam Console — Speaking Notes (~6 minutes)

**Launch (fresh every time):** stop any old server → `.\demos\week2_mam\run.ps1`  
**URL:** http://127.0.0.1:8765/  
**First screen must show:** green **COMPLETE**, **100/100 PASS**, not red “failed”.

---

## Opening

> “Ma’am, Month 1 of the GitHub plan is complete — M0 and M1.  
> Top strip: agent recording verified **100/100 bit-exact** offline.  
> Green COMPLETE is the product status. The ‘bug case’ tab is only a sample wrong LLM decision so we can show auto-bisect — Rewind itself did not fail.”

---

## Results 100× (default tab)

> “Press Re-run verify 100× if you want — same proof live, kill-switch on, zero API calls.”

---

## Try it live

> “Change city → Run agent + verify. Weather is live Open-Meteo; then offline verify.”

---

## Correct run → Bug case → Find the bug

> “Correct advice vs intentional wrong advice. Bisect stops at boundary #2 — same weather input, different LLM output.”

---

## Close

> “Same as CLI `fr record -- python` / `show` / `verify` / `bisect`. Plan: `docs/plan/month1-status.md`.”
