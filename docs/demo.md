# Rewind — Live Demo Runbook

A 3-minute live demonstration: record a **real, unmodified** AI agent making live API calls,
then replay it **bit-for-bit with the wifi off**. No incumbent (Langfuse, LangSmith, Arize)
can do this — they only show a static log; Rewind *re-executes* the run.

Everything here is real: real geocoding + weather APIs, a real LLM, real sampling. Nothing is
pre-scripted or faked.

---

## Before the demo (once, with internet)

```bash
cd rewind
uv sync                                   # install
echo 'NVIDIA_API_KEY=nvapi-...' > .env    # a free NVIDIA NIM key (git-ignored)
uv run fr --help                          # sanity check
```

The example agent (`examples/weather_agent.py`) is a normal tool-using agent: it geocodes a
city, fetches live weather, and asks an LLM for one line of umbrella advice — three real
network calls, and it has **no idea Rewind exists**.

---

## The demo (3 acts, ~3 minutes)

### Act 1 — Record a real agent, live

```bash
uv run fr record -- python examples/weather_agent.py "Delhi"
```

It runs the agent for real — you'll see live weather and a real LLM sentence — and Rewind
captures every step. Point out: *"I changed nothing in this agent. Rewind recorded it from
the outside."* Copy the `run` id it prints.

### Act 2 — Show what it captured

```bash
uv run fr show <run_id>
```

The decision timeline: the geocode call, the weather call, and the LLM call, each with a
hash-chain link. *"This is every nondeterministic thing the agent saw."*

### Act 3 — The moment: replay it offline 🔌

**Turn off the wifi.** Then:

```bash
uv run fr verify <run_id> --n 50
```

```
╭────────────────── run ac0e628f43e2 ──────────────────╮
│ ✓ BIT-EXACT   50/50 replays identical                │
│ 🔌 network kill-switch ON — 0 outbound calls         │
│ 3 boundaries · distinct fingerprints: 1 (expected 1) │
╰──────────────────────────────────────────────────────╯
```

Fifty perfect reproductions of a nondeterministic run — **with no internet**. That's the
whole product in one command: *reproduction is the prerequisite for every fix.*

---

## The killer contrast (optional, 20 seconds)

Run the live agent **twice** (wifi on) — the LLM wording differs each time (real sampling):

```bash
uv run fr record -- python examples/weather_agent.py "London"
uv run fr record -- python examples/weather_agent.py "London"
```

*"Live, it's different every run — that's why production agent bugs can't be reproduced.
Rewind's replay is identical every time."* If two runs diverge, you can also show:

```bash
uv run fr bisect <run_a> <run_b>     # names the first decision that differed
```

---

## What to say it is (and isn't)

- **It is:** a flight recorder + time-travel debugger for AI agents — `rr` (record/replay)
  meets `git bisect`, for nondeterministic LLM agents. Vendor-neutral, captured at the HTTP
  layer, so it works with any agent that uses `httpx`/OpenAI/Anthropic.
- **Today it does:** record any unmodified agent → replay bit-exact offline (proven) → show
  the timeline → bisect two runs.
- **Coming (roadmap):** time-travel scrubber, counterfactual "what-if" fork, and ML failure
  clustering across a fleet.

## If something goes wrong live

- **No internet at all:** the recording step needs it once. Record a run *before* you walk in
  (it's still a real run) — Acts 2 and 3 then work fully offline, which is the point.
- **API key/quota issue:** any previously recorded run replays offline forever; run
  `uv run fr runs` to list them and demo `show` + `verify` on an existing one.
- **Bisect doesn't diverge:** sampling is stochastic; it may take a couple of runs to get a
  good/bad pair. If you want it guaranteed, record the pair a few minutes early — still real.
