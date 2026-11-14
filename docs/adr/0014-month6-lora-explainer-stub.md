# ADR-0014: Month 6 — LoRA explainer stub, concurrent replay, and retention

- **Status:** Accepted
- **Date:** 2026-11-14
- **Deciders:** Naman Sharma (@namansh70747)

## Context

Month 5 delivered a scikit-learn failure-mode classifier and HDBSCAN clustering
(ADR-0013).  Month 6 (P5) closes the six-month roadmap with:

1. **A plain-English root-cause explainer** — the roadmap's headline P5 feature.
2. **Concurrent replay** — replay a cassette N times in parallel to measure throughput.
3. **Retention / GC** — delete old runs and unreachable blobs.
4. **Hardening** — the LoRA fine-tuning path is documented and its placeholder is
   shipped; actual training is deferred until a reviewed labeled corpus exists.

The core question is how to deliver the "plain-English root-cause" milestone honestly,
given that:

* A LoRA fine-tuned generative model requires a substantial labeled corpus, GPU
  training infrastructure, and a hallucination-resistant evaluation harness — none of
  which exist yet.
* ADR-0005 explicitly defers LoRA to "after the classifier and vector store are proven
  and a labeled corpus exists."
* Fabricating narration from an un-fine-tuned model would undermine the tool's
  trustworthiness exactly where it matters most.

## Decision

**Ship a deterministic, template-based explainer (`month6.explain`) that narrates
root cause from the classifier's label and recorded evidence.  Document the LoRA
fine-tuning path explicitly.  No model is called. Templates remain weak candidate explanations; deterministic wording does not establish factual grounding.**

Concretely:

- `explain(cassette, classifier_report, cluster_report)` returns a structured
  `rewind.explain.v1` document with a `cause` sentence, `next_steps` list, and a
  `lora_status` field that records the deferral decision.
- Each sentence is a fixed template keyed on the nine-class taxonomy from ADR-0005.
  An unknown label triggers a default sentence that cites the label explicitly.
- `concurrent_replay(cassette, run_fn, n, max_workers)` replays N times in parallel
  threads using `concurrent.futures.ThreadPoolExecutor`.
- `retention_gc(db_path, keep_last, max_age_days, dry_run)` deletes runs beyond the
  retention window, then calls `store.garbage_collect()` for orphaned blobs.
- A `rewind.benchmark.v1` schema records measured throughput evidence.

## Consequences

**Easier**

- Users get a human-readable candidate explanation keyed on a supplied label.
  The wording must not turn a label into proof of causality. This does not
  independently satisfy the original Month 6 release gates.
- The `lora_status` and `qualification` fields make the deferral explicit and
  machine-readable; a future phase can flip them when training is ready.
- Concurrent replay and the benchmark schema provide reproducible throughput evidence.
- Retention GC integrates with the existing `store.garbage_collect()` path.

**Harder / costs**

- The narration is template text, not a fluent natural-language generation.  Users
  who want richer prose must wait for the LoRA phase.
- Template maintenance grows linearly with the taxonomy; new failure modes require a
  new entry in `_CAUSE_SENTENCES` and `_NEXT_STEPS`.

## Alternatives Considered

- **Call an Ollama model for narration.**  Rejected: the existing `summaries.py`
  Ollama path is evidence-selection only, not root-cause narration, and local models
  can still hallucinate a confident wrong diagnosis for a debugging tool.

- **Skip the explainer entirely in Month 6.**  Rejected: the roadmap's P5 "Done when"
  criterion is "paste a failing run, get a plain-English root cause plus a suggested
  fix."  Template narration satisfies that criterion honestly.

- **Fine-tune LoRA now.**  Rejected for the same reasons as ADR-0005: data-hungry,
  hard to evaluate, and sequencing it after a proven classifier is safer.
