"""The ``fr`` command-line interface — record, inspect, replay, evaluate and export captured runs.

    fr record --provider nvidia          # record the example agent -> a run id
    fr show <run_id>                     # scrub the decision timeline
    fr verify <run_id> --n 50            # replay bit-exact, offline, zero API calls
    fr runs                              # list recorded runs

The API key is read from the environment or a git-ignored ``.env`` file.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from .commands import register
from .example_agent import make_example_run
from .providers import PROVIDERS
from .store import DEFAULT_DB, RunStore

if TYPE_CHECKING:
    from .boundary import Cassette

app = typer.Typer(add_completion=False, help="Rewind — flight recorder for AI agents.")
console = Console()


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Tiny, dependency-free .env loader: `KEY=value` lines; existing env wins."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _summarize(kind: str, response: Any) -> str:
    if kind != "http" or not isinstance(response, dict):
        return str(response)
    status = response.get("status", "?")
    body = response.get("body")
    if not isinstance(body, dict):
        return f"[{status}] (empty)"
    if "text" in body:
        return f"[{status}] {' '.join(str(body['text']).split())[:70]}"
    data = body.get("json", {})
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        try:
            text = data["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            text = json.dumps(data)
    return f"[{status}] {' '.join(str(text).split())[:70]}"


def _summarize_request(request: Any) -> str:
    """One-line summary of a boundary's request (the last user message for an LLM call)."""
    if not isinstance(request, dict):
        return "" if request is None else str(request)[:70]
    body = request.get("body")
    data = body.get("json") if isinstance(body, dict) else None
    if isinstance(data, dict):
        messages = data.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict) and "content" in last:
                return " ".join(str(last["content"]).split())[:70]
    return " ".join(str(request.get("url", request)).split())[:70]


@app.command()
def record(
    provider: Annotated[str, typer.Option(help="openai | nvidia | anthropic | gemini")] = "openai",
    model: Annotated[str | None, typer.Option(help="override the provider's default model")] = None,
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
    concurrent: Annotated[
        bool, typer.Option(help="opt-in async completion-order capture for scripts")
    ] = False,
    sources: Annotated[
        bool, typer.Option(help="capture selected clock/RNG/UUID sources for scripts")
    ] = False,
    command: Annotated[
        list[str] | None, typer.Argument(help="optional: -- python agent.py")
    ] = None,
) -> None:
    """Record the provider example, or a trusted script with -- python agent.py."""
    if command:
        if len(command) != 2 or Path(command[0]).name not in {"python", "python3", "python.exe"}:
            raise typer.BadParameter("supported command form: -- python path/to/agent.py")
        record_script_command(Path(command[1]), db, concurrent, sources)
        return
    _load_dotenv()
    if provider not in PROVIDERS:
        console.print(f"[red]unknown provider '{provider}'. choose from: {', '.join(PROVIDERS)}[/]")
        raise typer.Exit(2)
    prov = PROVIDERS[provider]
    api_key = os.environ.get(prov.key_env, "")
    if not api_key:
        console.print(f"[red]set {prov.key_env} (env or .env) to record a live {prov.name} run.[/]")
        raise typer.Exit(2)

    resolved = model or prov.default_model
    run = make_example_run(prov, model, api_key)
    console.print(f"recording one live [bold]{prov.name}[/] run ([cyan]{resolved}[/]) …")

    # Import here so a missing key errors cleanly above without needing httpx first.
    import httpx

    from .replay import record as do_record

    try:
        cassette = do_record(run, httpx.HTTPTransport(), provider=prov.name, model=resolved)
    except httpx.HTTPError as exc:
        console.print(f"[red]recording failed: {exc}[/]")
        raise typer.Exit(1) from exc

    store = RunStore(db)
    run_id = store.save(cassette)
    store.close()
    console.print(
        f"[green]recorded[/] {len(cassette.boundaries)} boundaries → run [bold]{run_id}[/]"
    )
    console.print(f"fingerprint : {cassette.fingerprint[:16]}…")
    console.print(f"output      : {cassette.final_output}")
    console.print(f"\nnext: [bold]fr show {run_id}[/]  ·  [bold]fr verify {run_id} --n 50[/]")


@app.command()
def show(
    run_id: str,
    at: Annotated[int | None, typer.Option(min=0, help="inspect state at boundary N")] = None,
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
) -> None:
    """Print a recorded run's decision timeline."""
    store = RunStore(db)
    try:
        if at is not None:
            try:
                console.print_json(data=store.snapshot_at(run_id, at))
            except ValueError as exc:
                raise typer.BadParameter(str(exc)) from exc
            return
        cassette = store.load(run_id)
    except KeyError:
        console.print(f"[red]run {run_id} not found[/]")
        raise typer.Exit(1) from None
    finally:
        store.close()

    if cassette.metadata.get("counterfactual"):
        console.print("QUARANTINED what-if · best-effort exploration", markup=False)
    table = Table(title=f"run {run_id}  ·  {cassette.provider}/{cassette.model}", show_lines=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("boundary", style="cyan")
    table.add_column("key")
    table.add_column("value")
    table.add_column("chain", style="dim")
    for b in cassette.boundaries:
        table.add_row(str(b.seq), b.kind, b.key, _summarize(b.kind, b.response), b.chain_hash[:8])
    console.print(table)
    console.print(f"fingerprint: [bold]{cassette.fingerprint[:16]}…[/]")
    console.print(f"output: {cassette.final_output}")


@app.command()
def verify(
    run_id: str,
    n: Annotated[int, typer.Option(min=1, help="number of replays")] = 50,
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
) -> None:
    """Replay a recorded run N times and prove it is bit-exact (zero API calls)."""
    from .replay import verify as do_verify

    store = RunStore(db)
    try:
        cassette = store.load(run_id)
    except KeyError:
        console.print(f"[red]run {run_id} not found[/]")
        raise typer.Exit(1) from None
    finally:
        store.close()

    if cassette.provider == "demo":
        from .demo import make_demo_run

        result = do_verify(cassette, make_demo_run(), n=n)
        console.print(str(result), markup=False)
        raise typer.Exit(0 if result.passed else 1)

    if cassette.provider not in PROVIDERS:
        console.print(
            f"[red]run {run_id} was recorded with unknown provider "
            f"'{cassette.provider}' — cannot rebuild the agent to replay it.[/]"
        )
        raise typer.Exit(2)
    prov = PROVIDERS[cassette.provider]
    run = make_example_run(prov, cassette.model or None, api_key="replay-needs-no-key")
    console.print(f"replaying run [bold]{run_id}[/] {n}x offline (network kill-switch on) ...")
    result = do_verify(cassette, run, n=n)
    style = "green" if result.passed else "red"
    console.print(f"[{style}]{result}[/]")
    raise typer.Exit(0 if result.passed else 1)


@app.command()
def runs(db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB) -> None:
    """List recorded runs."""
    store = RunStore(db)
    summaries = store.list_runs()
    store.close()
    if not summaries:
        console.print("no runs recorded yet — try [bold]fr record[/]")
        return
    table = Table(title="recorded runs")
    table.add_column("run id", style="bold")
    table.add_column("provider/model", style="cyan")
    table.add_column("boundaries", justify="right")
    table.add_column("recorded")
    for s in summaries:
        table.add_row(s.id, f"{s.provider}/{s.model}", str(s.n_boundaries), s.created_at)
    console.print(table)


@app.command()
def bisect(
    run_a: str,
    run_b: str,
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
    method: Annotated[str, typer.Option(help="auto | hash | align")] = "auto",
    embeddings: Annotated[
        Path | None, typer.Option(help="offline vector cache from embed-pair")
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="emit complete alignment and raw differences")
    ] = False,
) -> None:
    """Locate the first decision difference, preserving earlier source/metadata drift."""
    from .diagnosis import diagnose
    from .semantic import load_vectors

    left, right = _load_run(run_a, db), _load_run(run_b, db)
    try:
        vectors = (
            load_vectors(json.loads(embeddings.read_text()), left, right) if embeddings else None
        )
        report = diagnose(left, right, vectors=vectors, method=method)
    except (ValueError, TypeError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    first = report["primary_difference"]
    if json_output:
        console.print_json(data=report)
    elif first is None:
        console.print("no divergence — the recordings are identical", markup=False)
    else:
        console.print(
            f"first divergence at baseline #{first['a']} / candidate #{first['b']} · {first['category']}",
            markup=False,
        )
        console.print(first["summary"], markup=False)
        console.print(
            f"Method: {report['comparison_method']} / {report['alignment_method']}", markup=False
        )
        console.print_json(
            data={
                "left": first.get("left"),
                "right": first.get("right"),
                "raw_diff": first["raw_diff"],
                "upstream_context": report["upstream_context"],
            }
        )
        console.print(report["interpretation"], markup=False)
    raise typer.Exit(1 if first is not None else 0)


def _load_run(run_id: str, db: str) -> Cassette:
    from .boundary import Divergence
    from .integrity import validate

    store = RunStore(db)
    try:
        cassette = store.load(run_id)
        validate(cassette)
        return cassette
    except (KeyError, ValueError, Divergence) as exc:
        console.print(str(exc), style="red", markup=False)
        raise typer.Exit(1) from exc
    finally:
        store.close()


@app.command()
def demo(
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
    output: Annotated[Path, typer.Option(help="offline investigation dashboard")] = Path(
        ".rewind/demo.html"
    ),
    n: Annotated[int, typer.Option(min=1, max=1000, help="verification replays per run")] = 50,
) -> None:
    """Run the complete failure → bisect → safe fork → recovery demo, without API keys."""
    from dataclasses import asdict

    from .bisect import first_divergence
    from .dashboard import render_dashboard
    from .demo import make_demo_run, record_demo, recover_demo
    from .portable import export_run
    from .replay import verify as do_verify

    failed, passed = record_demo(720), record_demo(420)
    recovered = recover_demo(failed)
    cassettes = {
        "Failed · stale quote": failed,
        "Passing · fresh quote": passed,
        "Recovered · counterfactual": recovered,
    }
    evidence = {}
    store = RunStore(db)
    try:
        for label, cassette in cassettes.items():
            result = do_verify(cassette, make_demo_run(), n)
            if not result.passed:
                console.print(str(result), markup=False)
                raise typer.Exit(1)
            run_id = store.save(cassette)
            evidence[label] = {**asdict(result), "run_id": run_id}
            export_run(cassette, output.parent / f"{run_id}.rewind.json")
            console.print(f"{label}: {run_id} · PASS ({n} replays)", markup=False)
    finally:
        store.close()
    render_dashboard(cassettes, output, evidence)
    console.print(str(first_divergence(passed, failed)), markup=False)
    console.print("Recovery: 720 → 420; simulated reservation confirmed within the 500 budget.")
    console.print(f"Dashboard: {output.resolve()}", markup=False)
    console.print("All external services in this demo are simulated. No API keys or real bookings.")


@app.command()
def fork(
    run_id: str,
    price: Annotated[int, typer.Option(min=0, help="replacement price for the demo quote")] = 420,
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
    source: Annotated[Path | None, typer.Option(help="trusted recorded Python script")] = None,
    at: Annotated[int | None, typer.Option(min=0, help="boundary to replace")] = None,
    value: Annotated[Path | None, typer.Option(help="replacement response JSON file")] = None,
    mocks: Annotated[Path | None, typer.Option(help="JSON mapping: kind/key to response")] = None,
    policy: Annotated[
        Path | None, typer.Option(help="explicit per-tool live/classification manifest")
    ] = None,
) -> None:
    """Fork a trusted recorded script, or recover the bundled travel demo."""
    from .demo import recover_demo

    cassette = _load_run(run_id, db)
    try:
        if any(option is not None for option in (source, at, value, mocks, policy)):
            if source is None or at is None or value is None or mocks is None:
                raise ValueError("script forks require --source, --at, --value and --mocks")
            from .scripts import fork_script

            mapping = json.loads(mocks.read_text(encoding="utf-8"))
            if not isinstance(mapping, dict) or any(
                not isinstance(key, str) or "/" not in key or not all(key.split("/", 1))
                for key in mapping
            ):
                raise ValueError("mocks must be a JSON object with kind/key keys")
            from .policy import policy_from_manifest

            parsed_policy = policy_from_manifest(json.loads(policy.read_text())) if policy else None
            recovered = fork_script(
                cassette,
                source,
                at=at,
                value=json.loads(value.read_text(encoding="utf-8")),
                policy=parsed_policy,
                mocks={
                    (key.split("/", 1)[0], key.split("/", 1)[1]): result
                    for key, result in mapping.items()
                },
            )
        else:
            recovered = recover_demo(cassette, price)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    store = RunStore(db)
    try:
        child_id = store.save(recovered)
    finally:
        store.close()
    console.print(
        f"Counterfactual run (quarantined, best-effort): {child_id}\n{recovered.final_output}",
        markup=False,
    )


@app.command("export")
def export_command(
    run_id: str,
    output: Path,
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
) -> None:
    """Export a checksummed JSON recording. Review content before sharing."""
    from .portable import export_run

    export_run(_load_run(run_id, db), output)
    console.print(f"Exported: {output.resolve()}", markup=False)


@app.command("import")
def import_command(
    source: Path,
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
) -> None:
    """Validate and import a portable recording without executing code."""
    from .boundary import Divergence
    from .portable import import_run

    try:
        cassette = import_run(source)
    except (OSError, ValueError, Divergence) as exc:
        console.print(str(exc), style="red", markup=False)
        raise typer.Exit(1) from exc
    store = RunStore(db)
    try:
        run_id = store.save(cassette)
    finally:
        store.close()
    console.print(f"Imported: {run_id}", markup=False)


@app.command()
def dashboard(
    run_ids: Annotated[list[str], typer.Argument(help="one or more recorded run IDs")],
    output: Annotated[Path, typer.Option()] = Path(".rewind/dashboard.html"),
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
    alignment_model: Annotated[
        Path | None, typer.Option(help="optional local embedding model")
    ] = None,
) -> None:
    """Export an interactive, offline timeline and side-by-side comparison."""
    from .dashboard import render_dashboard

    render_dashboard(
        {rid: _load_run(rid, db) for rid in run_ids}, output, alignment_model=alignment_model
    )
    console.print(f"Dashboard: {output.resolve()}", markup=False)


@app.command()
def doctor() -> None:
    """Explain actual capture coverage and limitations (no credentials printed)."""
    import platform

    from . import __version__

    console.print(f"Rewind {__version__} · Python {platform.python_version()}")
    console.print(
        "Supported: httpx sync/async, buffered SSE, tools, source shims; opt-in concurrent schedule."
    )
    console.print(
        "Replay: recorded responses + best-effort Python socket guard; not an OS sandbox."
    )
    console.print(
        "Fork: exact prefix, intervention, explicit mocks by default; separate live allowlist API."
    )
    console.print(
        "Not captured: pre-existing clients, files, subprocesses, arbitrary global RNG/time."
    )
    console.print("Redaction: known patterns and sensitive fields; not complete PII detection.")
    console.print(
        "Pinned SDK and LangGraph integrations have local fixture tests; live services need qualification."
    )


@app.command("audit-corpus")
def audit_corpus_command(
    db: Annotated[Path, typer.Option(help="Existing local run store")] = Path(DEFAULT_DB),
    output: Annotated[Path | None, typer.Option(help="Optional JSON report path")] = None,
) -> None:
    """Scan stored recordings and blobs for integrity and known secret patterns."""
    from .corpus_audit import audit_corpus

    if not db.is_file():
        raise typer.BadParameter("Run store does not exist.", param_hint="--db")
    report = audit_corpus(db)
    rendered = json.dumps(report, indent=2)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    console.print(rendered, markup=False)
    if not report["passed"]:
        raise typer.Exit(1)


@app.command("eval")
def evaluate(
    n: Annotated[int, typer.Option(min=1, max=1000)] = 10,
    output: Annotated[Path | None, typer.Option(help="optional JSON evaluation report")] = None,
    budget: Annotated[
        int | None,
        typer.Option(
            help="Candidate budget. Offline replay fails if this changes a recorded outcome."
        ),
    ] = None,
) -> None:
    """Evaluate a labeled, synthetic corpus including the exact budget threshold."""
    from .demo import make_demo_run, record_demo, recover_demo
    from .replay import verify as do_verify

    rows = []
    for price in (0, 100, 300, 420, 499, 500, 501, 600, 720, 900, 1200, 5000):
        cassette = record_demo(price)
        result = do_verify(cassette, make_demo_run(), n)
        recovered = recover_demo(cassette)
        original = json.loads(cassette.final_output)
        correct = original["status"] == ("confirmed" if price <= 500 else "over_budget")
        rows.append(
            {
                "price": price,
                "replay_pass": result.passed,
                "replays": result.runs,
                "outcome_correct": correct,
                "recovery_pass": json.loads(recovered.final_output)["status"] == "confirmed",
            }
        )
    passed = all(r["replay_pass"] and r["outcome_correct"] and r["recovery_pass"] for r in rows)
    report: dict[str, Any] = {
        "corpus": "synthetic travel-budget-v1, 12 price cases; not production evidence",
        "cases": rows,
        "passed": passed,
    }
    if budget is not None:
        from .month5 import policy_gate

        gate = policy_gate(budget, repeats=n)
        report["policy_gate"] = gate
        report["passed"] = passed and bool(gate["passed"])
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    console.print_json(data=report)
    raise typer.Exit(0 if report["passed"] else 1)


@app.command()
def similar(
    run_id: str,
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
    limit: Annotated[int, typer.Option(min=1, max=100)] = 5,
) -> None:
    """Rank recordings by cosine similarity of event features (not an ML diagnosis)."""
    from .inspection import similarity

    target = _load_run(run_id, db)
    store = RunStore(db)
    try:
        scores = sorted(
            (
                (similarity(target, store.load(r.id)), r.id)
                for r in store.list_runs()
                if r.id != run_id
            ),
            reverse=True,
        )
    finally:
        store.close()
    console.print_json(
        data=[{"run_id": rid, "similarity": round(score, 4)} for score, rid in scores[:limit]]
    )


@app.command("record-script")
def record_script_command(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    db: Annotated[str, typer.Option()] = DEFAULT_DB,
    concurrent: Annotated[bool, typer.Option()] = False,
    sources: Annotated[bool, typer.Option()] = False,
    redaction_config: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
) -> None:
    """Execute and record a TRUSTED Python script (new httpx clients + stdout)."""
    from .redaction import RedactionRules, redaction_rules
    from .scripts import record_script

    rules = (
        RedactionRules.from_json(json.loads(redaction_config.read_text()))
        if redaction_config
        else RedactionRules()
    )
    with redaction_rules(rules):
        cassette = record_script(source, concurrent=concurrent, sources=sources)
    store = RunStore(db)
    try:
        run_id = store.save(cassette)
    finally:
        store.close()
    console.print(
        f"Recorded script: {run_id}\nNext: fr verify-script {run_id} {source}", markup=False
    )


@app.command("verify-script")
def verify_script_command(
    run_id: str,
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    n: Annotated[int, typer.Option(min=1)] = 10,
    db: Annotated[str, typer.Option()] = DEFAULT_DB,
    timing_scale: Annotated[float, typer.Option(min=0, max=100)] = 0.0,
    redaction_config: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
) -> None:
    """Replay a trusted script offline, checking source drift, boundaries and stdout."""
    from .scripts import verify_script

    try:
        from .redaction import RedactionRules, redaction_rules
        from .streaming import stream_playback_timing

        rules = (
            RedactionRules.from_json(json.loads(redaction_config.read_text()))
            if redaction_config
            else RedactionRules()
        )
        with redaction_rules(rules), stream_playback_timing(timing_scale):
            result = verify_script(_load_run(run_id, db), source, n)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(str(result), markup=False)
    raise typer.Exit(0 if result.passed else 1)


register(app)


@app.command("serve")
def serve_product(
    workspace: Annotated[
        Path, typer.Option(help="Trusted directory containing agent scripts")
    ] = Path(),
    db: Annotated[Path, typer.Option(help="Local recording database")] = Path(DEFAULT_DB),
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8766,
) -> None:
    """Start the local-only Rewind product workspace."""
    from .product.server import ProductServer

    server = ProductServer(("127.0.0.1", port), workspace, db)
    console.print(f"Rewind workspace: http://127.0.0.1:{server.server_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    """Keep redirected legacy terminals usable without changing their encoding."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")
    app()


if __name__ == "__main__":
    main()
