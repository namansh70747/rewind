# NVIDIA NIM: capture and offline replay

The NVIDIA Developer Program provides prototype endpoint access subject to its current limits and account eligibility. The default is `nvidia/nemotron-3-super-120b-a12b`; availability may change. Confirm the account's plan and quota before recording. This is a controlled NVIDIA example, not evidence for OpenAI or Anthropic gates.

Set `NVIDIA_API_KEY` securely in your shell environment (never commit or paste it into chat). Use a fresh key if one has been exposed. With the project environment installed:

```bash
uv run python examples/nvidia_agent.py record
uv run python examples/nvidia_agent.py verify --replays 50
```

The first command makes one live model request and stores a redacted recording under `.rewind/nvidia/`. The second replays it offline without the API key. To use another eligible model, pass `--model` at record time; verification reads the recorded model. A different `--output` preserves earlier recordings. Inspect output before sharing: redaction cannot guarantee removal of every secret or personal detail. Recorded content is sent to NVIDIA during capture, so use only data you are authorized to disclose. This simple example does not qualify streaming, retries or the complete Month 2 corpus.
