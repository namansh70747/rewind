# Contributing to Rewind

Thanks for your interest in Rewind — a flight recorder & time-travel debugger for
AI agents. This guide covers how to set up a dev environment, our workflow, and
how design decisions get made.

> [!IMPORTANT]
> **Rewind is pre-alpha and not yet implemented.** The design is complete and the
> repository is currently scaffolding + design docs. The most valuable
> contributions right now are **design feedback** and **ADR proposals** (see
> [The ADR process](#the-adr-process)). Code contributions will ramp up as the
> Phase 0 walking skeleton lands.

All participation is governed by our [Code of Conduct](./CODE_OF_CONDUCT.md).

## Table of contents

- [Ways to contribute](#ways-to-contribute)
- [Local development setup](#local-development-setup)
- [Running lint, types, and tests](#running-lint-types-and-tests)
- [Branch naming](#branch-naming)
- [Commit messages](#commit-messages)
- [The ADR process](#the-adr-process)
- [Pull request checklist](#pull-request-checklist)
- [How design decisions are made](#how-design-decisions-are-made)

## Ways to contribute

- **Design feedback** — open a discussion or issue on the architecture, CLI UX,
  storage format, or boundary model. This is the single most useful thing you can
  do right now.
- **ADR proposals** — propose a concrete design decision as an Architecture
  Decision Record (see below).
- **Docs** — improve the README, roadmap, or design docs.
- **Code** — once Phase 0 is underway, pick up an issue labeled
  `good first issue` or `help wanted`.

## Local development setup

Rewind uses [`uv`](https://docs.astral.sh/uv/) for environment and dependency
management. You need **Python 3.11+** (we support 3.11, 3.12, and 3.13).

```console
# Clone
$ git clone https://github.com/namansh70747/rewind.git
$ cd rewind

# Create the environment and install everything (incl. dev + optional extras)
$ uv sync --all-extras

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

## How design decisions are made

Rewind follows lightweight, ADR-driven governance (see
[`GOVERNANCE.md`](./GOVERNANCE.md)). Discussion happens in the open on issues and
PRs. Consensus is preferred; when it can't be reached, the Maintainer decides and
records the rationale in an ADR. Because the project is still pre-alpha, we bias
toward writing the decision down over shipping code that locks it in.
