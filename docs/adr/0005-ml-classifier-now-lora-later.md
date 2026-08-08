# ADR-0005: ML classifier now, LoRA failure-explainer later

- **Status:** Accepted
- **Date:** 2026-08-08
- **Deciders:** Naman Sharma (@namansh70747)

## Context

Once Rewind can record and bisect runs across a fleet, the natural next value is
**failure intelligence**: automatically grouping related failures and attaching a
root-cause label so engineers triage a cluster instead of one incident at a time. The
brief anticipates an eventual **LoRA "failure-explainer"** — a small local model
fine-tuned to narrate a run's root cause in plain English.

The question is one of sequencing and risk. A fine-tuned generative explainer is the
most impressive artifact, but it is also the highest-risk and most data-hungry: it
needs a substantial, well-labeled corpus, is hard to evaluate objectively, and can
hallucinate a confident-but-wrong explanation — which is especially damaging for a
*debugging* tool whose entire value is trustworthiness.

Crucially, Rewind generates its own labels for free. Auto-bisect already classifies
divergences into a taxonomy (arg-hallucination, tool-choice, sampling-flake,
tool-result-drift, retrieval-drift, loop, cost-blowup, truncation, api-error), and the
counterfactual fork can *manufacture* synthetic failures. That means a supervised
approach is viable without a manual labeling effort.

## Decision

**We will ship a real vector store plus a trained scikit-learn failure-mode classifier
first, and defer LoRA fine-tuning of a generative failure-explainer to a later phase.**

Concretely:

- Turn each run into **features + text → embeddings** (`sentence-transformers`) stored
  in **LanceDB**.
- Train a **scikit-learn classifier** to predict a root-cause label, and run
  **HDBSCAN** to discover clusters (with **UMAP** for visualization).
- Source training labels via **weak supervision** — bisect divergence classes,
  heuristic labeling functions, a local **Ollama** LLM-as-judge, and synthetic
  failures from the counterfactual fork — so no manual labeling is required.
- Treat the **LoRA failure-explainer as the final phase (P5)**, built only after the
  classifier and vector store are proven and a labeled corpus exists.

## Consequences

**Easier**

- We deliver measurable value early: a classifier's accuracy and clusters' coherence
  are objectively evaluable, unlike free-text explanations.
- Weak supervision makes the training set essentially free and self-refreshing as more
  runs are recorded and bisected.
- The classifier + embeddings become the **foundation** the LoRA phase builds on (its
  labels and corpus), so the ordering compounds rather than wastes effort.

**Harder / costs**

- Weak labels are noisy; we must accept and manage label noise (conflicting labeling
  functions, imperfect LLM-as-judge) rather than assume clean ground truth.
- A classifier gives a *label*, not a narrative — users get "sampling-flake," not a
  sentence — until the LoRA phase lands, so the plain-English payoff is delayed.
- We carry the ongoing cost of maintaining the labeling functions and the taxonomy as
  new failure modes appear.

## Alternatives Considered

- **Embeddings + clustering only (no classifier).** Purely unsupervised: embed runs
  and cluster them, no labels. Rejected because it can group similar failures but
  cannot *name* a root cause, and it wastes the free, high-quality labels that bisect
  already produces — leaving real supervisory signal on the table.

- **Fine-tune a generative model early.** Jump straight to the LoRA explainer as the
  headline ML feature. Rejected: it is the most data-hungry and hardest-to-evaluate
  option, and a hallucinated root cause would undermine the tool's credibility exactly
  where trust matters most. It is far safer to sequence it *after* a proven classifier
  and a labeled corpus exist.
