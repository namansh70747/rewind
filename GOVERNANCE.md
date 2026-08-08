# Governance

Rewind uses **lightweight, ADR-driven governance**. The goal is to keep the
project moving while making design decisions transparent and durable. This
document describes the roles, how decisions are made, how people join, and the
values that guide the project.

## Roles

### Maintainer

- **[@namansh70747](https://github.com/namansh70747)** (Naman Sharma) — project
  lead and author.

The Maintainer is responsible for the overall direction, has final say on
decisions when consensus cannot be reached, manages releases, and stewards the
governance process itself.

### Collaborators

- **[@aasthaaa25](https://github.com/aasthaaa25)**
- **[@kdua24](https://github.com/kdua24)**

Collaborators have write access, review and merge pull requests, triage issues,
and participate in design decisions via ADRs.

### Contributors

Anyone who opens an issue, proposes an ADR, files a PR, or gives design feedback
is a contributor. You do not need any special status to contribute — see
[`CONTRIBUTING.md`](./CONTRIBUTING.md).

## How decisions are made

Rewind decides via **Architecture Decision Records (ADRs)**, stored in
[`docs/adr/`](./docs/adr/):

1. Anyone may propose a decision by opening an ADR PR (status: **Proposed**).
2. Discussion happens in the open on the PR.
3. We seek **rough consensus** among Maintainer and Collaborators.
4. If consensus is reached, a Maintainer marks the ADR **Accepted** and merges.
5. If consensus cannot be reached, the **Maintainer decides** and records the
   rationale in the ADR.

Small, non-design changes (typos, bug fixes, tests) do not need an ADR — a normal
PR review is enough. When in doubt, write it down.

## Adding new collaborators

New Collaborators are invited based on a track record of sustained, high-quality
contribution — good ADRs, thoughtful reviews, and merged PRs. Any existing
Maintainer or Collaborator may nominate someone; the Maintainer confirms the
invitation. Collaborators are expected to follow this document and the
[Code of Conduct](./CODE_OF_CONDUCT.md).

Collaborators who wish to step back can move to emeritus status at any time; the
Maintainer may also move inactive Collaborators to emeritus after a prolonged
period of inactivity.

## Project values

- **Faithfulness first.** A replay that isn't bit-exact is worse than no replay.
  Correctness and reproducibility outrank features.
- **Decisions in the open.** If it shapes the design, it belongs in an ADR.
- **Vendor-neutral core.** Build on open standards (OpenTelemetry GenAI); keep
  vendor-specific integrations at the edges.
- **Laptop-first, zero-server.** Rewind should be free, local, and dependency-light
  wherever possible.
- **Respect privacy.** Recordings can contain secrets and PII; handling them
  safely is a first-class concern (see [`SECURITY.md`](./SECURITY.md)).
- **Be kind.** We follow the Contributor Covenant.

## Changing this document

Changes to governance are themselves made via PR, with the Maintainer's approval.
