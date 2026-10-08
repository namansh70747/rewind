"""Optional reproducible fleet analysis. Synthetic inputs never imply production accuracy."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from .inspection import features
from .redaction import redact
from .run_features import run_features

if TYPE_CHECKING:
    from pathlib import Path

    from .boundary import Cassette


def feature_text(cassette: Cassette) -> str:
    return (
        " ".join(
            token
            for key, count in sorted(features(cassette).items())
            for token in [key.replace(" ", "_")] * count
        )
        or "empty-run"
    )


def exploration_data(runs: dict[str, Cassette], vectors: Any) -> dict[str, Any]:
    """Neighbors use original feature space, never the lossy 2-D projection.

    Embed bounded, redacted timeline previews so the report works offline. Full
    recordings remain in the local store; truncation is explicit in the UI.
    """
    from sklearn.neighbors import NearestNeighbors

    ids = list(runs)
    distances, indices = (
        NearestNeighbors(metric="cosine")
        .fit(vectors)
        .kneighbors(vectors, n_neighbors=min(6, len(ids)))
    )
    return {
        "neighbor_metric": "cosine distance in original feature space (lower is closer)",
        "neighbors": {
            rid: [
                {"id": ids[int(j)], "distance": float(distance)}
                for distance, j in zip(ds, js, strict=True)
                if int(j) != i
            ][:5]
            for i, (rid, ds, js) in enumerate(zip(ids, distances, indices, strict=True))
        },
        "timelines": {
            rid: {
                "features": run_features(cassette),
                "fingerprint": cassette.fingerprint,
                "total_events": len(cassette.boundaries),
                "preview_limit": 200,
                "events": [
                    {
                        "seq": b.seq,
                        "kind": redact(b.kind),
                        "key": redact(b.key),
                        "request": json.dumps(redact(b.request), ensure_ascii=False)[:4000],
                        "response": json.dumps(redact(b.response), ensure_ascii=False)[:4000],
                        "payload_preview_limit": 4000,
                    }
                    for b in cassette.boundaries[:200]
                ],
            }
            for rid, cassette in runs.items()
        },
    }


def fleet_map(runs: dict[str, Cassette], min_cluster_size: int = 3) -> dict[str, Any]:
    import numpy as np
    from sklearn.cluster import HDBSCAN
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer

    if len(runs) < max(3, min_cluster_size):
        raise ValueError("need at least min_cluster_size (and at least 3) runs")
    vectorizer = TfidfVectorizer(token_pattern=r"\S+", lowercase=False)
    matrix = vectorizer.fit_transform([feature_text(c) for c in runs.values()])
    dense = matrix.toarray()
    labels = HDBSCAN(min_cluster_size=min_cluster_size, min_samples=2, copy=True).fit_predict(dense)
    dimensions = min(2, dense.shape[1] - 1)
    if dimensions >= 1:
        xy = TruncatedSVD(n_components=dimensions, random_state=42).fit_transform(matrix)
        if dimensions == 1:
            xy = np.column_stack([xy[:, 0], np.zeros(len(runs))])
    else:
        xy = np.zeros((len(runs), 2))
    return {
        "embedding": "TF-IDF event features (offline baseline)",
        **exploration_data(runs, dense),
        "projection": "TruncatedSVD",
        "clusterer": "HDBSCAN",
        "human_evaluation": "not performed",
        "points": [
            {"id": rid, "cluster": int(label), "x": float(point[0]), "y": float(point[1])}
            for rid, label, point in zip(runs, labels, xy, strict=True)
        ],
    }


def train_classifier(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Train/validate/test by caller-supplied scenario groups, with duplicate checks.

    Input contains text, label, group. Labels must come from a separate reviewed
    dataset. The model is returned as JSON weights, never executable pickle.
    """
    import numpy as np
    from sklearn.dummy import DummyClassifier
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import classification_report, f1_score
    from sklearn.model_selection import GroupShuffleSplit

    if len(samples) < 30:
        raise ValueError("need at least 30 labeled rows and multiple independent groups per class")
    texts = [str(s["text"]) for s in samples]
    labels = np.array([str(s["label"]) for s in samples])
    groups = np.array([str(s["group"]) for s in samples])
    seen: dict[str, str] = {}
    for text, group in zip(texts, groups, strict=True):
        if text in seen and seen[text] != group:
            raise ValueError("identical feature text crosses groups; avoid train/test leakage")
        seen[text] = group
    classes = set(labels)
    if len(classes) < 2:
        raise ValueError("need at least two classes")
    split = None
    for seed in range(100):
        trainval, test = next(
            GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed).split(
                texts, labels, groups
            )
        )
        train_local, val_local = next(
            GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed).split(
                trainval, labels[trainval], groups[trainval]
            )
        )
        train, val = trainval[train_local], trainval[val_local]
        if all(set(labels[index]) == classes for index in (train, val, test)):
            split = (train, val, test)
            break
    if split is None:
        raise ValueError("cannot create three group-disjoint splits containing every class")
    train, val, test = split
    vectorizer = TfidfVectorizer(token_pattern=r"\S+", lowercase=False)
    xtrain = vectorizer.fit_transform([texts[i] for i in train])
    xval = vectorizer.transform([texts[i] for i in val])
    xtest = vectorizer.transform([texts[i] for i in test])
    candidates = []
    for c in (0.1, 1.0, 10.0):
        model = LogisticRegression(C=c, max_iter=2000, random_state=42).fit(xtrain, labels[train])
        score = f1_score(labels[val], model.predict(xval), average="macro", zero_division=0)
        candidates.append((float(score), c, model))
    _, best_c, model = max(candidates, key=lambda item: item[0])
    predicted = model.predict(xtest)
    baseline = DummyClassifier(strategy="most_frequent").fit(xtrain, labels[train]).predict(xtest)
    return {
        "model": "TF-IDF + LogisticRegression",
        "selected_C": best_c,
        "dataset_sha256": hashlib.sha256(json.dumps(samples, sort_keys=True).encode()).hexdigest(),
        "held_out": [
            {
                "id": hashlib.sha256(json.dumps([str(groups[i]), texts[i]]).encode()).hexdigest(),
                "expected": str(labels[i]),
                "predicted": str(prediction),
            }
            for i, prediction in zip(test, predicted, strict=True)
        ],
        "test": classification_report(labels[test], predicted, output_dict=True, zero_division=0),
        "majority_baseline_macro_f1": float(
            f1_score(labels[test], baseline, average="macro", zero_division=0)
        ),
        "prompted_llm_baseline": "NOT MEASURED: roadmap Week 21 gate remains open",
        "split_groups": {
            name: sorted(set(groups[index]))
            for name, index in zip(("train", "validation", "test"), split, strict=True)
        },
        "json_model": {
            "vocabulary": vectorizer.vocabulary_,
            "idf": vectorizer.idf_.tolist(),
            "classes": model.classes_.tolist(),
            "coefficients": model.coef_.tolist(),
            "intercepts": model.intercept_.tolist(),
        },
    }


def embedding_index(runs: dict[str, Cassette], db_path: Path, model_path: Path) -> dict[str, Any]:
    """Optional roadmap stack. Model must already be available locally; no auto-download."""
    import lancedb
    import umap
    from sentence_transformers import SentenceTransformer
    from sklearn.cluster import HDBSCAN

    if not model_path.is_dir():
        raise ValueError("supply a local sentence-transformers model directory")
    if len(runs) < 5:
        raise ValueError("at least 5 runs required for embedding clusters")
    fingerprint = model_fingerprint(model_path)
    model = SentenceTransformer(str(model_path), local_files_only=True, device="cpu")
    vectors = model.encode([feature_text(c) for c in runs.values()], normalize_embeddings=True)
    labels = HDBSCAN(min_cluster_size=3, min_samples=2, copy=True).fit_predict(vectors)
    xy = umap.UMAP(
        n_neighbors=min(15, len(runs) - 1), n_components=2, init="random", random_state=42
    ).fit_transform(vectors)
    rows = [
        {
            "id": rid,
            "vector": v.tolist(),
            "cluster": int(label),
            "x": float(p[0]),
            "y": float(p[1]),
            "model_fingerprint": fingerprint,
        }
        for rid, v, label, p in zip(runs, vectors, labels, xy, strict=True)
    ]
    db = lancedb.connect(str(db_path))
    # New immutable generation: never overwrite a previous index.
    import uuid

    table_name = "runs_" + uuid.uuid4().hex[:12]
    db.create_table(table_name, data=rows)
    return {
        "table": table_name,
        **exploration_data(runs, vectors),
        "model_fingerprint": fingerprint,
        "feature_schema": "event-count-tokens-v1",
        "model": str(model_path),
        "points": [{k: v for k, v in row.items() if k != "vector"} for row in rows],
        "human_evaluation": "not performed",
    }


def weak_labels(cassette: Cassette) -> list[str]:
    """Conservative observed-symptom votes; abstain when evidence is insufficient."""
    votes: set[str] = set()
    identities = []
    for b in cassette.boundaries:
        identities.append((b.kind, b.key))
        response = b.response
        if isinstance(response, dict):
            error = response.get("transport_error", {})
            if isinstance(error, dict) and "Timeout" in str(error.get("type", "")):
                votes.add("transport-timeout")
            status = response.get("status")
            if isinstance(status, int) and status == 429:
                votes.add("rate-limit")
            if isinstance(status, int) and status >= 500:
                votes.add("provider-error")
            if status == "over_budget":
                votes.add("budget-exceeded")
            if response.get("ok") is False:
                votes.add("tool-error")
    if len(identities) > 10 and len(set(identities)) <= 2:
        votes.add("repeated-boundaries")
    return sorted(votes)


def predict_cause(model: dict[str, Any], cassette: Cassette) -> dict[str, Any]:
    """Infer from exported JSON weights; never unpickle or load executable models."""
    import math
    from collections import Counter

    model = model.get("json_model", model)
    vocabulary = model["vocabulary"]
    idf = model["idf"]
    coefficients = model["coefficients"]
    intercepts = model["intercepts"]
    classes = model["classes"]
    if len(idf) > 1_000_000 or len(classes) < 2:
        raise ValueError("invalid or oversized JSON model")
    if any(len(row) != len(idf) for row in coefficients) or len(intercepts) != len(coefficients):
        raise ValueError("inconsistent model dimensions")
    vector = [0.0] * len(idf)
    counts = Counter(feature_text(cassette).split())
    for token, count in counts.items():
        if token in vocabulary:
            index = vocabulary[token]
            if type(index) is not int or not 0 <= index < len(idf):
                raise ValueError("invalid vocabulary index")
            vector[index] = count * float(idf[index])
    norm = math.sqrt(sum(v * v for v in vector))
    if not norm:
        return {"label": None, "reason": "out-of-vocabulary run; model abstained"}
    vector = [v / norm for v in vector]
    logits = [
        sum(w * x for w, x in zip(row, vector, strict=True)) + bias
        for row, bias in zip(coefficients, intercepts, strict=True)
    ]
    if len(classes) == 2 and len(logits) == 1:
        probability = 1 / (1 + math.exp(-max(-700, min(700, logits[0]))))
        probabilities = [1 - probability, probability]
    elif len(logits) == len(classes):
        exponentials = [math.exp(v - max(logits)) for v in logits]
        probabilities = [v / sum(exponentials) for v in exponentials]
    else:
        raise ValueError("invalid class dimensions")
    best = max(range(len(classes)), key=lambda i: probabilities[i])
    return {
        "label": classes[best],
        "probabilities": dict(zip(classes, probabilities, strict=True)),
        "interpretation": "Model suggestion; reliability depends on the supplied labels/corpus.",
    }


def compare_baseline(report: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Score supplied baseline predictions on exactly the classifier's held-out rows.

    This computes evidence, not a claim that the submitted labels were independently
    produced. Run baseline inference before opening held-out answers; retain provenance.
    """
    from sklearn.metrics import classification_report, f1_score

    held_out = report.get("held_out", [])
    metadata = baseline.get("provenance", {})
    if not held_out or not all(metadata.get(k) for k in ("provider", "model", "prompt_sha256")):
        raise ValueError("held-out report and provider/model/prompt_sha256 provenance required")
    rows = baseline.get("predictions", [])
    predictions = {row["id"]: row["label"] for row in rows}
    identifiers = {row["id"] for row in held_out}
    if len(predictions) != len(rows) or set(predictions) != identifiers:
        raise ValueError("baseline must provide exactly one prediction for every held-out ID")
    expected = [row["expected"] for row in held_out]
    learned = [row["predicted"] for row in held_out]
    prompted = [predictions[row["id"]] for row in held_out]
    labels = sorted(set(expected))
    if any(p not in labels for p in prompted):
        raise ValueError("baseline labels must use the evaluated taxonomy")
    classifier_f1 = float(f1_score(expected, learned, average="macro", zero_division=0))
    baseline_f1 = float(f1_score(expected, prompted, average="macro", zero_division=0))
    return {
        "dataset_sha256": report["dataset_sha256"],
        "held_out_count": len(held_out),
        "classifier_macro_f1": classifier_f1,
        "prompted_baseline_macro_f1": baseline_f1,
        "classifier_beats_baseline": classifier_f1 > baseline_f1,
        "baseline_per_class": classification_report(
            expected, prompted, output_dict=True, zero_division=0
        ),
        "baseline_provenance": metadata,
        "qualification": "Submitted predictions; data review and independent baseline provenance require human verification.",
    }


def model_fingerprint(model_path: Path) -> str:
    """Identify local weights/config/tokenizer contents, independent of directory name."""
    digest = hashlib.sha256()
    paths = sorted(
        p
        for p in model_path.rglob("*")
        if p.is_file()
        and p.suffix in {".json", ".txt", ".safetensors", ".bin", ".model"}
        and ".cache" not in p.parts
    )
    if not paths:
        raise ValueError("model directory contains no weights/config files")
    for path in paths:
        digest.update(str(path.relative_to(model_path)).encode())
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def search_embeddings(
    cassette: Cassette, db_path: Path, table_name: str, model_path: Path, limit: int = 5
) -> list[dict[str, Any]]:
    """Query a persisted generation using the exact same local model contents."""
    import lancedb
    from sentence_transformers import SentenceTransformer

    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    table = lancedb.connect(str(db_path)).open_table(table_name)
    first = table.search().limit(1).to_list()
    if not first or first[0].get("model_fingerprint") != model_fingerprint(model_path):
        raise ValueError("index model fingerprint differs; rebuild with this model")
    model = SentenceTransformer(str(model_path), local_files_only=True, device="cpu")
    query = model.encode([feature_text(cassette)], normalize_embeddings=True)[0].tolist()
    from lancedb.query import LanceVectorQueryBuilder

    builder = table.search(query)
    if not isinstance(builder, LanceVectorQueryBuilder):
        raise RuntimeError("index did not return a vector query")
    rows = builder.distance_type("cosine").limit(limit).to_list()
    return [
        {k: v for k, v in row.items() if k not in {"vector", "model_fingerprint"}} for row in rows
    ]
