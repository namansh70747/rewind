# Contributing to Rewind

Thanks for your interest in Rewind — a flight recorder & time-travel debugger for
AI agents. This guide covers how to set up a dev environment, our workflow, and
how design decisions get made.

> Rewind is a working local alpha. Start with `fr demo`, then run the test and
> quality gates below. The wider six-month plan remains future work.

All participation is governed by our [Code of Conduct](./CODE_OF_CONDUCT.md).

## Table of contents

- [Ways to contribute](#ways-to-contribute)
- [Local development setup](#local-development-setup)
- [Running lint, types, and tests](#running-lint-types-and-tests)
- [Branch naming](#branch-naming)
- [Commit messages](#commit-messages)
- [The ADR process](#the-adr-process)
- [Pull request checklist](#pull-request-checklist)
- [Reviewing pull requests](#reviewing-pull-requests)
- [Merge requirements](#merge-requirements)
- [How design decisions are made](#how-design-decisions-are-made)

## Ways to contribute

- **Design feedback** — open a discussion or issue on the architecture, CLI UX,
  storage format, or boundary model. Include a reproducible example when possible.
- **ADR proposals** — propose a concrete design decision as an Architecture
  Decision Record (see below).
- **Docs** — improve the README, roadmap, or design docs.
- **Code** — pick up an issue labeled
  `good first issue` or `help wanted`.

## Local development setup

Rewind uses [`uv`](https://docs.astral.sh/uv/) for environment and dependency
management. You need **Python 3.11+** (we support 3.11, 3.12, and 3.13).

```console
# Clone
$ git clone https://github.com/namansh70747/rewind.git
$ cd rewind

# Create the environment and install everything (incl. dev + optional extras)
$ uv sync --extra dev --extra docs --extra integrations --extra tui --extra ml

# Install pre-commit hooks
$ uv run pre-commit install
```

The import package is `flightrecorder` and the CLI entry point is `fr`.

## Running lint, types, and tests

Run everything at once:

```console
$ make check          # runs ruff, mypy, and pytest
```

Or run each tool individually:

```console
$ uv run ruff check .        # lint
$ uv run ruff format .       # format
$ uv run mypy                # type-check
$ uv run pytest              # tests
```

Please make sure `make check` passes before opening a PR. `pre-commit` will run
the fast checks (ruff) automatically on commit.

## Branch naming

Branch off `main` using a short, descriptive, kebab-case name prefixed by type:

```
feat/boundary-log-schema
fix/replay-clock-drift
docs/roadmap-p2
chore/ci-python-313
adr/0007-storage-format
```

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/). The format
is:

```
<type>(<optional scope>): <description>

[optional body]

[optional footer(s)]
```

Common types: `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`,
`chore`. Examples:

```
feat(recorder): capture wall-clock boundaries
fix(replay): engage network kill-switch before PLAYBACK
docs(adr): add ADR-0003 on the four interceptor modes
```

Keep the subject line under ~72 characters and in the imperative mood.

## The ADR process

Non-trivial design decisions are recorded as **Architecture Decision Records**
in [`docs/adr/`](./docs/adr/). An ADR is a short Markdown file that captures the
context, the decision, and its consequences.

1. Copy the template to `docs/adr/NNNN-short-title.md` (next sequential number).
2. Fill in **Status** (Proposed / Accepted / Superseded), **Context**,
   **Decision**, and **Consequences**.
3. Open a PR titled `adr: NNNN <title>`.
4. Discussion happens on the PR. When consensus is reached, a maintainer sets the
   status to **Accepted** and merges.

Superseding an old decision? Add a new ADR that references and supersedes the
old one, and update the old one's status.

## Pull request checklist

Before requesting review, confirm:

- [ ] The change is scoped to one logical concern.
- [ ] `make check` passes locally (ruff, mypy, pytest).
- [ ] New/changed behavior has tests (once code exists to test).
- [ ] Docs updated if behavior or UX changed.
- [ ] `CHANGELOG.md` updated under `## [Unreleased]` if user-facing.
- [ ] Commits follow Conventional Commits.
- [ ] For design-shaping changes, a corresponding ADR exists or is linked.

## Reviewing pull requests

Every change to `main` goes through a pull request and **at least one approving
review from a Code Owner** ([`.github/CODEOWNERS`](./.github/CODEOWNERS) routes the
request to the right area owner automatically). Reviewing well is a first-class
contribution — a good review is specific, kind, and focused on what actually matters.

**As an author:** keep PRs small and single-purpose, write a clear description of
*what* and *why* (link the issue/ADR), and make sure CI is green before requesting
review. Respond to every comment; resolve a thread only when it's actually addressed.

**As a reviewer**, work down this checklist:

- [ ] **Correctness** — does it do what the PR says, including edge cases (loops,
      retries, streaming, async, errors)?
- [ ] **Faithfulness first** — could this change let replay diverge *silently*? Any
      new nondeterministic boundary (clock, RNG, uuid, network, tool I/O, global
      state) **must** be captured, and the divergence oracle must still fail loud.
      This is the project's #1 invariant — treat a silent-divergence risk as blocking.
- [ ] **Respects the ADRs** — playback ≠ re-execution ([ADR-0006](./docs/adr/0006-replay-is-playback-not-re-execution.md)),
      capture at the transport layer ([ADR-0007](./docs/adr/0007-capture-at-http-transport-layer.md)),
      our own schema with OTel at the edges ([ADR-0008](./docs/adr/0008-internal-recording-schema-otel-as-export.md)).
      A change that contradicts an accepted ADR needs a *superseding* ADR, not a quiet override.
- [ ] **Definition of Done** — does the change round-trip (record → replay bit-exact →
      timeline → test)? Are there tests, and is the record→replay→`verify` canary still green?
- [ ] **Scope & simplicity** — one concern per PR; no unrelated churn; the simplest
      thing that works.
- [ ] **Security/PII** — no secrets in code, fixtures, or recordings; redaction still
      runs before storage.
- [ ] **Docs & changelog** — user-facing changes update docs and `CHANGELOG.md`.

**Review etiquette:** review within ~1 business day so nobody is blocked. Distinguish
**blocking** comments (correctness, faithfulness, security, ADR conflicts) from
**non-blocking** suggestions (prefix those with `nit:`). Approve once the DoD is met —
don't hold a PR hostage over style. If you open a PR, you don't review/approve your own;
the third teammate stays unblocked on their own work.

## Merge requirements

A PR can be merged into `main` when **all** of these are true (enforced by branch
protection):

- **≥ 1 approving review from a Code Owner**, and all review threads resolved.
- **All required status checks pass** — `lint` and `test (3.11 / 3.12 / 3.13)` — and the
  branch is up to date with `main`.
- **Re-approval after new pushes** — pushing new commits dismisses stale approvals, so a
  fresh review is required (no sneaking changes in after approval).
- **Linear history** — merge via **squash** or **rebase** (no merge commits); keep the
  squash subject a clean Conventional Commit.

The PR author merges once these are green. Direct pushes to `main` are reserved for
maintainer setup/emergencies (admins can bypass) — normal work always goes through a PR.

## How design decisions are made

Rewind follows lightweight, ADR-driven governance (see
[`GOVERNANCE.md`](./GOVERNANCE.md)). Discussion happens in the open on issues and
PRs. Consensus is preferred; when it can't be reached, the Maintainer decides and
records the rationale in an ADR. Because the project is still pre-alpha, we bias
toward writing the decision down over shipping code that locks it in.
