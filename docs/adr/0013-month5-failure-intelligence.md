# ADR-0013: Synthetic failure intelligence before a real fleet

Status: accepted for the Month 5 software path. The real-fleet and prompted-LLM gates stay open.

## Context

Weeks 19–22 ask for run features, nearest failures, HDBSCAN clusters, a weak-label
classifier, a zero-cost eval gate, a timeline query DSL, and “this matches cluster
X” on a fresh failure. The author’s 672-tool / 10-provider fleet and an independently
collected prompted-LLM baseline are not in this repository.

## Decision

Ship those workflows on recordings the caller already has, and prove them on a
synthetic three-family corpus:

- Neighbors use cosine similarity of event-count features. Prompts are not embedded.
- Clusters reuse the offline TF-IDF / HDBSCAN map. A fresh run inherits the majority
  cluster of its nearest saved runs, plus the most common weak label.
- The eval gate replays recorded budget fixtures. A candidate budget that changes an
  outcome fails the gate without a new model call.
- The query DSL gains three fixed phrases (`every tool error`, `every retry`,
  `first context > N tokens`). It still does not evaluate code.
- Retries and cost are recorded only from explicit `attempt` and `cost_usd` fields.

Sentence-transformers, LanceDB and UMAP remain the optional local-model path already
behind `fr index-embeddings`. This ADR does not download a model and does not treat
synthetic purity as human agreement or production accuracy.

## Consequences

`fr similar`, `fr query`, `fr match`, `fr fleet-map` and `fr eval` are enough to demo
Month 5 on local recordings. M5.2 stays open until someone supplies a prompted baseline
through `fr compare-baseline`. M5.4 stays open until real fleet recordings exist.
