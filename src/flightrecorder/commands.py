"""Roadmap CLI extensions, kept separate from the basic recording commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.console import Console

from .store import DEFAULT_DB, RunStore

if TYPE_CHECKING:
    from .boundary import Cassette

console = Console()


def _load(rid: str, db: str) -> Cassette:
    store = RunStore(db)
    try:
        return store.load(rid)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    finally:
        store.close()


def _json(value: Any, output: Path | None = None) -> None:
    rendered = json.dumps(value, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    console.print(rendered, markup=False)


def register(app: typer.Typer) -> None:
    @app.command("trace-export")
    def trace_export(
        run_id: str, output: Path, format: str = "perfetto", db: str = DEFAULT_DB
    ) -> None:
        """Export Perfetto Trace Event JSON or OTLP/HTTP JSON."""
        from .interop import write_trace

        if format not in {"perfetto", "otlp", "otlp-protobuf"}:
            raise typer.BadParameter("format must be perfetto, otlp or otlp-protobuf")
        write_trace(_load(run_id, db), output, format)
        console.print(str(output), markup=False)

    @app.command("trace-import")
    def trace_import(source: Path, db: str = DEFAULT_DB) -> None:
        """Ingest OTLP spans as non-replayable observational evidence."""
        from .interop import ingest_otlp

        cassette = ingest_otlp(json.loads(source.read_text()))
        store = RunStore(db)
        try:
            console.print(store.save(cassette))
        finally:
            store.close()

    @app.command("diagnose")
    def diagnose_command(
        run_a: str,
        run_b: str,
        db: str = DEFAULT_DB,
        output: Path | None = None,
        model: Path | None = None,
    ) -> None:
        """Align inserted/deleted steps and name evidence-based divergence categories."""
        from .diagnosis import diagnose

        _json(diagnose(_load(run_a, db), _load(run_b, db), model_path=model), output)

    @app.command("hash-bisect")
    def hash_bisect_command(run_a: str, run_b: str, db: str = DEFAULT_DB) -> None:
        """Validate traces, then binary-search the first unequal chain link."""
        from .diagnosis import hash_bisect

        index = hash_bisect(_load(run_a, db), _load(run_b, db))
        _json({"first_difference": index})
        raise typer.Exit(1 if index is not None else 0)

    @app.command("query")
    def query_command(run_id: str, expression: str, db: str = DEFAULT_DB) -> None:
        """Query boundary fields: fr query RUN 'first response.status >= 400'."""
        from .query import query

        try:
            _json(query(_load(run_id, db), expression))
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

    @app.command("tui")
    def tui_command(run_id: str, db: str = DEFAULT_DB) -> None:
        """Open Textual terminal scrubber (requires the tui extra)."""
        try:
            from .tui import TimelineApp
        except ImportError as exc:
            raise typer.BadParameter("install the tui extra: pip install '.[tui]'") from exc
        TimelineApp(_load(run_id, db)).run()

    @app.command("storage-stats")
    def storage_stats(db: str = DEFAULT_DB) -> None:
        """Show compressed content-addressed storage and reference counts."""
        store = RunStore(db)
        try:
            _json(store.storage_stats())
        finally:
            store.close()

    @app.command("benchmark")
    def benchmark_command(
        output: Path = Path(".rewind/benchmark.json"),
        steps: Annotated[int, typer.Option(min=10, max=100000)] = 1000,
    ) -> None:
        """Measure capture/storage/snapshot overhead on a labeled synthetic workload."""
        from .evaluation import benchmark

        _json(benchmark(output.parent / "benchmark.db", steps), output)

    @app.command("eval-fixtures")
    def eval_fixtures(
        manifest: Path, n: Annotated[int, typer.Option(min=1)] = 5, output: Path | None = None
    ) -> None:
        """Execute trusted recorded-script fixtures as an actual pass/fail gate."""
        from .evaluation import evaluate_manifest

        try:
            report = evaluate_manifest(manifest, n)
        except (ValueError, OSError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        _json(report, output)
        raise typer.Exit(0 if report["passed"] else 1)

    @app.command("fleet-map")
    def fleet_map_command(
        db: str = DEFAULT_DB,
        output: Path = Path(".rewind/fleet.json"),
        min_cluster_size: Annotated[int, typer.Option(min=2)] = 3,
    ) -> None:
        """Cluster saved runs with TF-IDF/HDBSCAN (offline baseline, requires ml extra)."""
        from .fleet import fleet_map

        store = RunStore(db)
        try:
            report = fleet_map(
                {r.id: store.load(r.id) for r in store.list_runs()}, min_cluster_size
            )
        finally:
            store.close()
        _json(report, output)
        from .fleet_view import render_fleet

        render_fleet(report, output.with_suffix(".html"))

    @app.command("train-classifier")
    def train_classifier_command(
        dataset: Path, output: Path = Path(".rewind/classifier.json")
    ) -> None:
        """Fit group-split supervised classifier from reviewed {text,label,group} JSON rows."""
        from .fleet import train_classifier

        try:
            report = train_classifier(json.loads(dataset.read_text()))
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _json(report, output)

    @app.command("index-embeddings")
    def index_embeddings(
        model: Path, db: str = DEFAULT_DB, output: Path = Path(".rewind/embeddings.json")
    ) -> None:
        """Use a LOCAL sentence-transformers model with LanceDB/HDBSCAN/UMAP."""
        from .fleet import embedding_index

        store = RunStore(db)
        try:
            report = embedding_index(
                {r.id: store.load(r.id) for r in store.list_runs()},
                output.parent / "vectors",
                model,
            )
        finally:
            store.close()
        _json(report, output)
        from .fleet_view import render_fleet

        render_fleet(report, output.with_suffix(".html"))

    @app.command("fork-script")
    def fork_script_command(
        run_id: str, source: Path, at: int, value: Path, mocks: Path, db: str = DEFAULT_DB
    ) -> None:
        """Intervene on a trusted script; --value JSON and --mocks {kind/key: value}."""
        from .scripts import fork_script

        mapping = json.loads(mocks.read_text())
        resolved = {tuple(key.split("/", 1)): response for key, response in mapping.items()}
        if any(len(key) != 2 for key in resolved):
            raise typer.BadParameter("mock keys must have kind/key syntax")
        typed = {(str(key[0]), str(key[1])): response for key, response in resolved.items()}
        child = fork_script(
            _load(run_id, db), source, at=at, value=json.loads(value.read_text()), mocks=typed
        )
        store = RunStore(db)
        try:
            console.print(store.save(child))
        finally:
            store.close()

    @app.command("audit-script")
    def audit_script(run_id: str, source: Path, db: str = DEFAULT_DB) -> None:
        """Verify a trusted script and report observed blocked Python network operations."""
        from .offline import offline_guard
        from .scripts import verify_script

        with offline_guard() as audit:
            result = verify_script(_load(run_id, db), source, 1)
        _json(
            {
                "passed": result.passed,
                "detail": result.detail,
                "blocked_operations": audit.blocked_operations,
                "coverage": "Python sockets only; not proof of all filesystem/native I/O coverage",
            }
        )
        raise typer.Exit(0 if result.passed else 1)

    @app.command("snapshot")
    def snapshot_command(run_id: str, at: int, db: str = DEFAULT_DB) -> None:
        """Inspect state through persisted content-addressed checkpoints."""
        store = RunStore(db)
        try:
            _json(store.snapshot_at(run_id, at))
        finally:
            store.close()

    @app.command("predict-cause")
    def predict_command(run_id: str, model: Path, db: str = DEFAULT_DB) -> None:
        """Predict from a reviewed JSON classifier; unseen vocabulary causes abstention."""
        from .fleet import predict_cause

        _json(predict_cause(json.loads(model.read_text()), _load(run_id, db)))

    @app.command("weak-labels")
    def labels_command(run_id: str, db: str = DEFAULT_DB) -> None:
        """Report conservative observed-symptom labels for human review."""
        from .fleet import weak_labels

        _json({"votes": weak_labels(_load(run_id, db)), "review_required": True})

    @app.command("compare-baseline")
    def baseline_command(report: Path, baseline: Path, output: Path | None = None) -> None:
        """Compare independently collected prompted baseline predictions on held-out IDs."""
        from .fleet import compare_baseline

        try:
            _json(
                compare_baseline(json.loads(report.read_text()), json.loads(baseline.read_text())),
                output,
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise typer.BadParameter(str(exc)) from exc

    @app.command("policy-set")
    def policy_set(
        path: Path,
        kind: str,
        key: str,
        mutating: bool = True,
        live: bool = False,
    ) -> None:
        """Edit explicit per-tool policy JSON; defaults are mutating and mocked."""
        from .policy import policy_from_manifest

        data: dict[str, Any] = (
            json.loads(path.read_text()) if path.exists() else {"version": 1, "tools": []}
        )
        try:
            policy_from_manifest(data)
            rows = [row for row in data["tools"] if (row["kind"], row["key"]) != (kind, key)]
            data["tools"] = [*rows, {"kind": kind, "key": key, "mutating": mutating, "live": live}]
            policy_from_manifest(data)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _json(data, path)
        console.print(
            "Saved policy only. No tools executed; live entries require application authorization."
        )

    @app.command("search-embeddings")
    def embedding_search_command(
        run_id: str, index: Path, table: str, model: Path, limit: int = 5, db: str = DEFAULT_DB
    ) -> None:
        """Find nearby runs in a persisted LanceDB generation using its local model."""
        from .fleet import search_embeddings

        _json(search_embeddings(_load(run_id, db), index, table, model, limit))

    @app.command("summarize-clusters")
    def summarize_command(
        report: Path,
        model: str,
        output: Path,
        db: str = DEFAULT_DB,
        endpoint: str = "http://127.0.0.1:11434",
    ) -> None:
        """Ask an already-running local Ollama model to narrate aggregated cluster evidence."""
        from .fleet_view import render_fleet
        from .summaries import summarize_clusters

        data = json.loads(report.read_text())
        store = RunStore(db)
        try:
            runs = {point["id"]: store.load(point["id"]) for point in data["points"]}
        finally:
            store.close()
        result = summarize_clusters(data, runs, model, endpoint)
        _json(result, output)
        render_fleet(result, output.with_suffix(".html"))
        if any(value["status"] != "generated" for value in result["summaries"].values()):
            raise typer.Exit(1)

    @app.command("release-check")
    def release_check_command(manifest: Path, output: Path | None = None) -> None:
        """Fail closed unless every required release gate has digest-checked reviewed evidence."""
        from .release import release_check

        try:
            report = release_check(manifest)
        except (ValueError, OSError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        _json(report, output)
        raise typer.Exit(0 if report["checklist_complete"] else 1)
