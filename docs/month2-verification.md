# Month 2 verification — local evidence, 9 November 2026

The Month 2 goal is faithful capture and verification; a passing local test does not establish universal agent support. This page records the scope of checks on the development machine. It does not claim the original M2 gate has passed.

## Real-provider evidence

Three controlled recordings from 2 November 2026 were replayed again on 9 November using the checked-in trusted scripts, source-hash checks and the offline Python socket guard. Each produced one output and one fingerprint across 50/50 replays. The product database stores the recordings locally; these IDs and results are not a signed attestation or a published fixture corpus.

| Local run | Provider / model | Scope |
|---|---|---|
| `fe359d631368` | Groq / `openai/gpt-oss-20b` | One non-streaming HTTP model response |
| `0e708305f15f` | Groq / `openai/gpt-oss-20b` | One streaming HTTP response containing a tool call; tool execution was not performed |
| `b96c8a68382d` | Google Gemini / `gemini-2.5-flash` | One non-streaming HTTP model response |

These captures do not qualify OpenAI or Anthropic endpoints; Groq's OpenAI-compatible API and its `openai/` model name do not mean an OpenAI provider endpoint was tested. Live provider quota, model availability and costs depend on the account. Do not store credentials in a recording or repository.

## Stored-corpus audit

`fr audit-corpus --db PATH` checks integrity of logical recordings, scans their structured data and all stored blob objects for the built-in redaction patterns, and examines decoded stream bytes. The product's **Settings → Audit stored corpus** invokes the same check. The report includes identifiers and counts, not matched values. An empty store does not pass.

On the development store on 9 November 2026, the audit examined 26 recordings and 23 blobs: zero integrity failures, zero known-pattern matches and zero invalid/unreadable blobs. The result includes simulated recordings and the controlled live runs above; it applies only to that store and those known patterns. It does **not** scan SQLite free pages, exports, backups or every possible secret; manually review artifacts before sharing. Tests use synthetic secrets and include encoded query-key redaction and a secret split into encoded stream storage.

## Remaining original Month 2 gates

- Real unmodified OpenAI and Anthropic agents, including streaming tool calls and retries, still require their own recorded corpus and offline verification. Existing Groq/Gemini checks are a separate free-provider milestone.
- Recorded replay is only as complete as captured boundaries. Python socket auditing is best-effort, not an OS sandbox; native I/O, subprocesses, filesystem and arbitrary globals are not comprehensively intercepted.
- The storage format remains **proposed**, not frozen: ADR 0010 and compatibility fixtures still require maintainer review. A measured real-workload footprint budget and broader corpus are pending.
- The 26-run scan is a limited known-pattern result, not proof that all stored content or backups are free of secrets.

The current outcome is substantial implementation and controlled validation, not complete acceptance of the original M2 gate.
