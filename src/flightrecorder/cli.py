"""The ``fr`` command-line interface — the Phase-0 walking-skeleton surface.

    fr record --provider nvidia          # record the bundled example agent -> a run id
    fr record -- python agent.py         # record an unmodified agent script (M1)
    fr show <run_id>                     # print the decision timeline
    fr verify <run_id> --n 50            # replay bit-exact, offline, zero API calls
    fr verify <run_id> --strict          # also fail on uncaptured time/random/uuid
    fr runs                              # list recorded runs

The API key is read from the environment or a git-ignored ``.env`` file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any, Optional

import typer
from rich.console import Console
from rich.table import Table

from .example_agent import make_example_run
from .providers import PROVIDERS
from .store import DEFAULT_DB, RunStore

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


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def record(
    ctx: typer.Context,
    provider: Annotated[
        Optional[str], typer.Option(help="openai | nvidia | anthropic (bundled agent)")
    ] = None,
    model: Annotated[str | None, typer.Option(help="override the provider's default model")] = None,
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
) -> None:
    """Record a run: bundled agent (``--provider``) or unmodified script (``-- python agent.py``)."""
    _load_dotenv()
    extras = list(ctx.args)
    if extras:
        _record_unmodified(extras, db=db, provider=provider or "unmodified", model=model or "")
        return

    chosen = provider or "openai"
    if chosen not in PROVIDERS:
        console.print(f"[red]unknown provider '{chosen}'. choose from: {', '.join(PROVIDERS)}[/]")
        raise typer.Exit(2)
    prov = PROVIDERS[chosen]
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


def _record_unmodified(
    argv: list[str], *, db: str, provider: str, model: str
) -> None:
    """M1 path: ``fr record -- python agent.py [args]``."""
    from .capture import capture
    from .runner import make_runner

    try:
        runner = make_runner(argv)
    except (ValueError, FileNotFoundError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(2) from exc

    console.print(f"recording unmodified agent [cyan]{' '.join(argv)}[/] …")
    store = RunStore(db)
    try:
        with capture(store, provider=provider, model=model) as cap:
            runner()
    except Exception as exc:
        store.close()
        console.print(f"[red]recording failed: {exc}[/]")
        raise typer.Exit(1) from exc

    assert cap.cassette is not None and cap.run_id is not None
    store.close()
    console.print(
        f"[green]recorded[/] {len(cap.cassette.boundaries)} boundaries → run [bold]{cap.run_id}[/]"
    )
    console.print(f"fingerprint : {cap.cassette.fingerprint[:16]}…")
    console.print(f"\nnext: [bold]fr show {cap.run_id}[/]  ·  [bold]fr bisect[/] / verify via capture API")


@app.command()
def show(
    run_id: str,
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
) -> None:
    """Print a recorded run's decision timeline."""
    store = RunStore(db)
    try:
        cassette = store.load(run_id)
    except KeyError:
        console.print(f"[red]run {run_id} not found[/]")
        raise typer.Exit(1) from None
    finally:
        store.close()

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
    n: Annotated[int, typer.Option(help="number of replays")] = 50,
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Fail if agent code reads time, random, uuid4, or os.urandom outside the recorder.",
        ),
    ] = False,
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

    if cassette.provider not in PROVIDERS:
        console.print(
            f"[red]run {run_id} was recorded with unknown provider "
            f"'{cassette.provider}' — cannot rebuild the agent to replay it.[/]"
        )
        raise typer.Exit(2)
    prov = PROVIDERS[cassette.provider]
    run = make_example_run(prov, cassette.model or None, api_key="replay-needs-no-key")
    mode = " · strict" if strict else ""
    console.print(
        f"replaying run [bold]{run_id}[/] {n}x offline (network kill-switch on){mode} ..."
    )
    result = do_verify(cassette, run, n=n, strict=strict)
    style = "green" if result.passed else "red"
    console.print(f"[{style}]{result.verdict}[/]")
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
) -> None:
    """Find the first diverging decision between two recorded runs (e.g. a good vs bad run)."""
    from .bisect import first_divergence

    store = RunStore(db)
    try:
        cassette_a = store.load(run_a)
        cassette_b = store.load(run_b)
    except KeyError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from None
    finally:
        store.close()

    result = first_divergence(cassette_a, cassette_b)
    if not result.diverged:
        console.print("[green]no divergence — the two runs are identical[/]")
        return

    console.print(f"[bold red]first divergence at boundary #{result.index}[/]  {result.reason}")
    if result.a is not None or result.b is not None:
        table = Table(show_header=True)
        table.add_column("run", style="bold")
        table.add_column("boundary", style="cyan")
        table.add_column("request")
        table.add_column("response")
        # Render each side independently so a length divergence (only one side has the extra
        # boundary) still shows the lone step, and the request side makes an input diff obvious.
        for name, boundary in ((run_a, result.a), (run_b, result.b)):
            if boundary is None:
                table.add_row(name, "[dim](no boundary — run ended here)[/]", "", "")
            else:
                table.add_row(
                    name,
                    f"{boundary.kind}:{boundary.key}",
                    _summarize_request(boundary.request),
                    _summarize(boundary.kind, boundary.response),
                )
        console.print(table)
    raise typer.Exit(1)  # diverged -> non-zero, useful as a CI gate


if __name__ == "__main__":
    app()
