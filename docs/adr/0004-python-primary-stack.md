# ADR-0004: Python 3.11+ as the primary stack

- **Status:** Accepted
- **Date:** 2026-08-08
- **Deciders:** Naman Sharma (@namansh70747)

## Context

Rewind must live *inside* the same process as the agent it records, because faithful
capture means intercepting the agent's boundary reads in-process — LLM client calls,
tool invocations, the clock, RNG, and hash seeding. The choice of implementation
language is therefore constrained by where agents actually run and by what
interception mechanisms are available there.

The overwhelming majority of agent frameworks and LLM SDKs — OpenAI, Anthropic,
LangGraph, and the wider ecosystem — are **Python-first**. The ML layer Rewind depends
on (sentence-transformers, scikit-learn, hdbscan, umap-learn) is also Python-native.
And Python offers `wrapt`, a mature library for transparent, well-behaved function
wrapping, which is precisely the mechanism the uniform interceptor needs.

We must decide the primary language and toolchain now, because it determines how
interception is implemented and how contributors build and test the project.

## Decision

**We will build Rewind primarily in Python 3.11+**, with:

- **`uv`** for environment and dependency management,
- **`ruff`** for linting/formatting and **`mypy`** for static typing,
- **`pytest`** for tests, and
- **`wrapt`-based interception** (function wrappers + decorators + determinism shims)
  as the mechanism behind the uniform boundary interceptor.

Python 3.11+ is the floor so we can rely on modern typing and performance
improvements.

## Consequences

**Easier**

- We run in the same language and process as the agents we record, so interception is
  direct and idiomatic — `wrapt` lets us wrap client and tool calls transparently.
- The entire ML layer is native to the ecosystem; no cross-language bridge is needed
  between capture and analytics.
- Contributors get a fast, modern toolchain (`uv`/`ruff`/`mypy`/`pytest`) with a low
  barrier to entry, matching where agent developers already work.

**Harder / costs**

- Python's performance ceiling and the GIL constrain the highest-throughput paths;
  concurrent replay (P5) will need care.
- Dynamic interception via `wrapt` is powerful but subtle — monkeypatching semantics,
  async wrapping, and import-order effects must be handled carefully.
- Determinism shims (clock, RNG, `PYTHONHASHSEED`) must cover Python's many sources of
  nondeterminism precisely, or replay drifts.

## Alternatives Considered

- **A Go core.** Go would offer stronger concurrency, a lower performance floor, and
  easy single-binary distribution — attractive for the high-throughput replay and
  fleet paths. Rejected **for now** on ecosystem fit: agents and their SDKs live in
  Python, so a Go core would sit *outside* the process it needs to instrument and
  couldn't intercept in-process boundary reads cleanly, and the ML stack would be a
  poor fit. If a specific hot path later demands it, a targeted Go (or Rust) component
  behind a stable interface remains an option — this ADR would then be revisited.
