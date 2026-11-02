# Release execution guide

This candidate has local tests and runnable workflows. It is **not yet a published
Week-26 release**. The original roadmap requires real data, independent review and
release credentials that are not present in this workspace.

## Prepared release automation

- The ordinary CI workflow checks Python 3.11, 3.12 and 3.13.
- Docs builds upload a Pages artifact. After the maintainer enables GitHub Pages
  with **GitHub Actions** as its source, a main-branch docs build can deploy through
  the `github-pages` environment. Pull requests only build; they do not deploy.
- The release workflow can build a candidate manually. Tagged builds additionally
  check that the commit belongs to main, that the package version matches the tag,
  and that the reviewed evidence checklist passes.
- PyPI publication uses a trusted publisher through a `pypi` environment. The
  maintainer must verify ownership of the distribution name and configure that
  publisher and environment protection. No credentials belong in source code.

No workflow was run remotely, no tag was created, and no package was published by
this local work. Repository writes remain blocked by the connected integration.

## Evidence checklist

```bash
fr release-check docs/release-evidence/checklist.json --output .rewind/release-status.json
```

The initial checklist deliberately blocks publication. Each required gate needs
an explicit reviewer/reference and a file under the checklist's directory, plus
its SHA-256 digest. Changed, absent or out-of-directory artifacts block the check.
The command checks local evidence integrity; it cannot authenticate a reviewer or
prove the scientific validity of submitted results. Code Owner review and protected
environments remain necessary. Do not fill pass entries with synthetic evidence
for real-provider, real-fleet or real-demo gates.

## Timed stream playback

```bash
fr verify-script RUN_ID agent.py --timing-scale 1 --n 1
```

The default scale 0 is fast playback; 1 paces chunks to recorded relative offsets;
0.5 runs twice as fast. Monotonic deadlines reduce cumulative drift, but scheduler
precision is best effort. Pauses exceeding 30 seconds fail explicitly. Capture is
still buffered, uses decoded HTTP bytes, and does not preserve compressed wire
packets or arbitrary binary data. Redaction can merge chunks to prevent leakage.

Python callers can use `with stream_playback_timing(1):` from
`flightrecorder.streaming` around replay/verification.

## Custom redaction

Keep extra secret rules in an ignored local file such as `.rewind/redaction.json`:

```json
{"extra_keys": ["student_id"], "literals": ["YOUR_PRIVATE_LITERAL"]}
```

```bash
fr record-script agent.py --redaction-config .rewind/redaction.json
fr verify-script RUN_ID agent.py --redaction-config .rewind/redaction.json
```

Use the same rules for recording and replay. Rules only add redaction; they never
disable the built-in detectors. Literal matching uses exact replacement, not
user-supplied regular expressions. Configuration contents are not saved into the
cassette. Known-field redaction is still not a guarantee of detecting every PII type.

## Local cluster summaries

Start your own Ollama instance with an already-downloaded model, then run:

```bash
fr fleet-map --output .rewind/fleet.json
fr summarize-clusters .rewind/fleet.json MODEL_NAME .rewind/narrated.json
```

Only a local HTTP endpoint is accepted. The model selects one to three IDs from
redacted aggregate feature weights. Unknown/duplicate IDs, extra prose or invalid
schema fail closed. Rewind renders the displayed explanation from the selected
recorded labels and weights; the model cannot insert its own causal narrative.
Weights are explicitly not event counts. Failed calls are recorded as unavailable
and the command exits nonzero. Noise cluster -1 is not narrated.

Actual Ollama 0.40.1 CPU inference with a pinned official Qwen2.5-0.5B GGUF passed
this selection contract for three synthetic clusters. The previous free-text
version invented maintenance/traffic claims; the evidence-selection design removes
that unsupported prose channel. See `release-evidence/ollama-qualification.json`.
Selection relevance and real cluster coherence still require human review.

Reproduce against an already-running local model:

```bash
python examples/ollama_smoke.py YOUR_LOCAL_MODEL
```

The example uses 15 synthetic recordings in manually assigned groups. It does not
claim clustering accuracy or real fleet validation. Neither the script nor the
summarizer downloads weights. For the full acceptance sequence and exact external
inputs, see [the completion checklist](completion-checklist.md).

## Viewer interoperability

Use `fr trace-export RUN_ID trace.pb --format otlp-protobuf` for collectors such as
Phoenix that require `application/x-protobuf`. `--format otlp` remains OTLP JSON;
not every collector accepts that content type. The protobuf export preserves the
same trace/span IDs and captured evidence without rewriting the recording.

The exported Perfetto JSON was loaded by the official TraceProcessor engine with
all seven demo boundaries present. This is an actual external-parser check, not
just a schema check. Timestamp fields still explicitly represent ordinal positions.

Phoenix 20.19.0 accepted the unchanged protobuf file, persisted all seven demo spans
and displayed their captured inputs/outputs in the browser. Its JSON receiver returned
HTTP 415, which is why the protobuf option is provided. Because these exports have
ordinal timestamps, the default last-seven-days filter hides them; open the specific
trace directly or choose a date range including January 1970.

For an already-running local Phoenix server:

```bash
fr trace-export RUN_ID .rewind/trace.pb --format otlp-protobuf
curl -X POST http://localhost:6006/v1/traces -H 'Content-Type: application/x-protobuf' --data-binary @.rewind/trace.pb
```

## Clean wheel on each operating system

```bash
uv build
python scripts/wheel_smoke.py
```

This creates a fresh temporary virtual environment, installs only the built wheel
and its runtime dependencies, runs the installed console script outside the source
tree, checks 150 demo replays and executes evaluation. Results land in
`.rewind/wheel-smoke/`. CI prepares Ubuntu, Windows and macOS jobs with separate
artifacts. Local Linux passed; other operating systems await remote execution.
