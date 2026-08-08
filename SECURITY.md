# Security Policy

Thank you for helping keep Rewind and its users safe. This document explains
which versions are supported, how to report a vulnerability privately, what to
expect after you report, and — importantly — the data-handling considerations
that are specific to a tool that records AI-agent traces.

## Supported versions

Rewind is **pre-alpha**. Only the latest `0.0.x` line receives any security
attention, and even that is best-effort while the project is under active,
pre-release development.

| Version  | Status              | Supported          |
| -------- | ------------------- | ------------------ |
| `0.0.x`  | Pre-alpha (current) | :white_check_mark: (best-effort) |
| `< 0.0`  | N/A                 | :x:                |

> [!NOTE]
> Because Rewind is not yet implemented, there are no released binaries to patch
> yet. This policy is in place from day one so that reporting channels exist as
> soon as code lands.

## Reporting a vulnerability

**Please do not open public issues for security problems.** Report privately via
either of the following:

1. **Email:** [nsharma_be24@thapar.edu](mailto:nsharma_be24@thapar.edu) — use a
   subject line starting with `[SECURITY]`.
2. **GitHub private security advisories:** open a draft advisory at
   <https://github.com/namansh70747/rewind/security/advisories/new> (Security →
   Report a vulnerability).

When reporting, please include, if possible:

- A description of the issue and its potential impact.
- Steps to reproduce or a proof of concept.
- Affected version/commit and environment details.
- Any suggested remediation.

Please do not publicly disclose the issue until we have had a chance to
investigate and, where applicable, release a fix. We support coordinated
disclosure and will credit reporters who wish to be acknowledged.

## Response-time expectations

As a pre-alpha, single-maintainer project, these are targets rather than
guarantees:

| Stage                          | Target                 |
| ------------------------------ | ---------------------- |
| Acknowledge receipt            | within 3 business days |
| Initial assessment / triage    | within 7 business days |
| Fix or mitigation plan         | within 30 days         |

We will keep you updated as we work through triage and remediation.

## Data-handling: recordings may contain secrets and PII

> [!IMPORTANT]
> **This is the security consideration most specific to Rewind.** Rewind records
> the nondeterministic inputs of an agent run — LLM prompts and completions, tool
> inputs and outputs, and external API responses. These **can and often will
> contain secrets (API keys, tokens, credentials) and personally identifiable
> information (PII).** Treat every recording as sensitive by default.

Rewind treats safe handling of this data as a first-class, security-relevant
design commitment:

- **Redaction on export.** When a recording is exported or shared, Rewind applies
  redaction so that sensitive material is stripped or masked before the artifact
  leaves the machine that made it.
- **Secret stripping.** The recorder is designed to detect and strip common
  secret patterns (keys, tokens, authorization headers, and configured custom
  patterns) at capture and/or export time, so they are not persisted in the clear.
- **Local-first by default.** Rewind is laptop-first and zero-server; recordings
  stay on your machine unless you deliberately export or share them.

These are design commitments for the implementation as it lands; until then,
assume no protections exist and handle recordings with maximum care.

### Do not commit recordings

**Never commit Rewind recordings or their data artifacts to a repository.** They
may embed secrets and PII, and once pushed they are effectively public/permanent.
The project's [`.gitignore`](./.gitignore) excludes Rewind data artifacts
(`.rewind/`, `recordings/`, `blobs/`, `*.db`, `*.sqlite*`, `*.parquet`,
`lancedb/`, `models/`, `.env`) by default — please keep those ignores in place
and double-check `git status` before committing.
