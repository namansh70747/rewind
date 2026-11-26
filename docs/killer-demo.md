# Killer demo (Month 6 ⭐)

A newcomer should reproduce this from a clone, with **no API key**.

```bash
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
source .venv/bin/activate
python -m pip install -e '.[dev]'
fr demo
```

Open `.rewind/demo.html`. Then, using IDs printed by `fr demo`:

```bash
fr verify FAIL_ID --n 50
fr bisect PASS_ID FAIL_ID
fr fork FAIL_ID --price 420
fr dashboard FAIL_ID PASS_ID FORK_ID --output .rewind/investigation.html
```

## What you must see

1. Failed run: quote **720** vs budget **500**.
2. `fr verify` — 50/50 offline, kill-switch on.
3. `fr bisect` — first difference at **boundary #3**.
4. `fr fork --price 420` — recovery with mutating tools mocked.
5. Original failed cassette unchanged.

Live NVIDIA/Gemini record → replay → fork is documented in
[Month 3 workflow](month3-time-travel.md). Those calls cost quota; the killer
demo above does not.

## Embeddings extra (Month 5)

Optional nearest-neighbour search with a local encoder:

```bash
python -m pip install -e '.[ml,embeddings]'
fr similar RUN_ID
fr fleet-map --output .rewind/fleet.json
```

Without the extra, event-feature cosine `fr similar` and TF-IDF `fr fleet-map`
still run via `.[ml]`.
