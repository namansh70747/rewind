# Actual local-model investigation

This example captures real Ollama inference and simulated reservation tools. It
is a controlled local debugging scenario, not the author's production fleet.
The package includes a pre-rendered offline dashboard and portable recordings.

## Record and replay

Use a local Ollama instance with an already-installed model:

```bash
python examples/local_agent_demo.py record YOUR_LOCAL_MODEL
```

The script makes three actual local inference calls: an over-budget recording,
an affordable recording, and a separately allowlisted live-model continuation
of a price-change fork. Reservation tools never contact a booking service.
A fourth recording injects `{"action":"book"}` into the affordable run's model
response and continues with explicit mocks. That injected response is clearly
counterfactual and is never presented as a genuine model answer.

Stop the dedicated test Ollama instance, then run:

```bash
python examples/local_agent_demo.py verify
```

Verification needs no running model or model weights. It checks the source digest,
replays every recording fifty times, compares outputs and hash chains, checks the
explicit intervention outcome, and writes `.rewind/local-agent/demo.html` plus
`qualification.json`. Use the same `--output DIRECTORY` for both commands if you
choose another directory. Recording requires an empty directory to preserve
existing evidence.

## What actually happened in this environment

- Ollama 0.40.1 used the pinned official Qwen2.5-0.5B GGUF identified in
  `release-evidence/local-agent-qualification.json`. An explicit ChatML template
  was supplied; the template and runtime identity are retained in that evidence.
- At price 720 with budget 500, the simulated tool returned `over_budget`.
- At price 420, the small model still selected `reject`; the run returned `declined`.
- Changing only the quote and allowing a new local model call also returned
  `declined`. **The live price-only fork did not recover.**
- A separate model-decision intervention at boundary 2 changed the recorded answer
  to `book` and the mocked continuation returned `confirmed` at price 420.
- After the test server was terminated and connection failure confirmed, all four
  recordings replayed 50/50 times with identical outputs and fingerprints:
  **200 server-off replays passed**.
- The actual-model label, counterfactual lineage, recovered output, desktop/mobile
  layout and offline browser behavior passed the checked-in browser test.

The top-level demonstration pass means faithful replay plus a working explicit
intervention. It does **not** mean the original model mistake was fixed, the
price-only live fork recovered, or the original real-fleet release gate passed.
Earlier unsuccessful price-only attempts remain in the evidence record.

## Why this is useful

Rewind preserves the model's actual poor decision, lets the reader inspect the
captured request/response, and distinguishes an ineffective quote intervention
from a decision intervention. An injected answer is an experiment about downstream
behavior, not evidence that a model would produce that answer unaided.

```bash
REWIND_CHROMIUM=/path/to/chromium node tests/browser/local_agent.cjs path/to/demo.html
```

The optional browser check requires Playwright. The core record/verify example uses
only the ordinary Rewind runtime dependencies and an existing Ollama service for
recording. It downloads nothing automatically.
