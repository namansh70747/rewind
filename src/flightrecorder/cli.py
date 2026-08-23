"""The ``fr`` command-line interface.

    fr record --provider nvidia                    # bundled example agent
    fr record --provider nvidia -- python agent.py # unmodified agent (Phase 1)
    fr show <run_id>                               # decision timeline
    fr verify <run_id> --n 50                      # bit-exact replay, offline
    fr runs                                        # list recorded runs
    fr bisect <run_a> <run_b>                      # first diverging decision

The API key is read from the environment or a git-ignored ``.env`` file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .example_agent import make_example_run
from .providers import PROVIDERS
from .store import DEFAULT_DB, RunStore

if TYPE_CHECKING:
    from .boundary import Cassette
    from .replay import VerifyResult

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
    command: Annotated[
        list[str] | None,
        typer.Argument(
            metavar="[-- python your_agent.py [ARGS]]",
            help="record an unmodified agent (its LLM + tool HTTP calls); "
            "omit to run the bundled example",
        ),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option(help="openai | nvidia | anthropic (required for the bundled example)"),
    ] = None,
    model: Annotated[str | None, typer.Option(help="override the provider's default model")] = None,
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
) -> None:
    """Record a live run — an unmodified agent (``-- python agent.py``) or the bundled example."""
    _load_dotenv()
    if command:
        # Unmodified agents pick their own HTTP endpoints; do not invent a provider label.
        _record_command(command, provider=provider or "", model=model or "", db=db)
        return

    resolved_provider = provider or "openai"
    if resolved_provider not in PROVIDERS:
        console.print(
            f"[red]unknown provider '{resolved_provider}'. choose from: {', '.join(PROVIDERS)}[/]"
        )
        raise typer.Exit(2)
    prov = PROVIDERS[resolved_provider]
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
    _print_recorded(run_id, cassette)


def _record_command(argv: list[str], *, provider: str, model: str, db: str) -> None:
    """Record an unmodified agent given as ``python agent.py [args]`` — captured at the httpx layer."""
    import httpx

    from .capture import capture
    from .runner import canonicalize_command, encode_command, make_runner

    try:
        stored_argv = canonicalize_command(argv)
        run = make_runner(stored_argv)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(2) from exc

    console.print(f"recording [bold]{' '.join(stored_argv)}[/]")
    console.print("capturing every httpx call the agent makes (LLM + tools)\n")
    store = RunStore(db)
    try:
        with capture(
            store, provider=provider, model=model, command=encode_command(stored_argv)
        ) as cap:
            run()
    except httpx.HTTPError as exc:
        console.print(f"\n[red]the agent's HTTP call failed while recording: {exc}[/]")
        raise typer.Exit(1) from exc
    finally:
        store.close()

    if cap.cassette is None or cap.run_id is None:  # pragma: no cover - defensive
        console.print("[red]nothing was recorded.[/]")
        raise typer.Exit(1)
    if not cap.cassette.boundaries:
        console.print("[yellow]recorded 0 boundaries — the agent made no httpx calls.[/]")
    else:
        kinds = _boundary_kind_summary(cap.cassette)
        console.print(f"\ncaptured [bold]{len(cap.cassette.boundaries)}[/] boundaries ({kinds})")
    _print_recorded(cap.run_id, cap.cassette)


def _boundary_kind_summary(cassette: Cassette) -> str:
    """Human summary of boundary kinds from the real cassette (not hard-coded)."""
    counts: dict[str, int] = {}
    for b in cassette.boundaries:
        counts[b.kind] = counts.get(b.kind, 0) + 1
    return ", ".join(f"{n} {kind}" for kind, n in counts.items())


def _print_recorded(run_id: str, cassette: Cassette) -> None:
    """Shared 'recorded' summary for both the bundled agent and a captured command."""
    console.print(f"[green]recorded[/] → run [bold]{run_id}[/]")
    console.print(f"fingerprint : {cassette.fingerprint[:16]}…")
    if cassette.provider or cassette.model:
        label = "/".join(p for p in (cassette.provider, cassette.model) if p)
        console.print(f"label       : {label}")
    console.print(f"\nnext: [bold]fr show {run_id}[/]  ·  [bold]fr verify {run_id} --n 50[/]")


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

    title = f"run {run_id}"
    if cassette.provider or cassette.model:
        title += f"  ·  {'/'.join(p for p in (cassette.provider, cassette.model) if p)}"
    table = Table(title=title, show_lines=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("boundary", style="cyan")
    table.add_column("key")
    table.add_column("value")
    table.add_column("chain", style="dim")
    for b in cassette.boundaries:
        table.add_row(str(b.seq), b.kind, b.key, _summarize(b.kind, b.response), b.chain_hash[:8])
    console.print(table)
    console.print(f"fingerprint: [bold]{cassette.fingerprint[:16]}…[/]")
    if cassette.command:
        from .runner import decode_command

        console.print(f"command: {' '.join(decode_command(cassette.command))}")
    if cassette.final_output:
        console.print(f"output: {cassette.final_output}")
    console.print(f"boundaries: {len(cassette.boundaries)} ({_boundary_kind_summary(cassette)})")


@app.command()
def verify(
    run_id: str,
    n: Annotated[int, typer.Option(help="number of replays")] = 50,
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
) -> None:
    """Replay a recorded run N times and prove it is bit-exact (zero API calls)."""
    store = RunStore(db)
    try:
        cassette = store.load(run_id)
    except KeyError:
        console.print(f"[red]run {run_id} not found[/]")
        raise typer.Exit(1) from None
    finally:
        store.close()

    console.print(f"replaying run [bold]{run_id}[/] · {n}x · network kill-switch on\n")
    if cassette.command:
        # An arbitrary agent captured via `fr record -- …`: re-run its own code in replay mode.
        # Silence the agent's own stdout across the N replays so only the verdict shows.
        import contextlib
        import io

        from .capture import verify_run
        from .runner import decode_command, make_runner

        try:
            run = make_runner(decode_command(cassette.command))
        except ValueError as exc:
            console.print(f"[red]cannot replay this run: {exc}[/]")
            raise typer.Exit(2) from None
        with contextlib.redirect_stdout(io.StringIO()):
            result = verify_run(cassette, run, n=n)
    else:
        # The bundled example agent: rebuild it from the recorded provider/model.
        from .replay import verify as do_verify

        if cassette.provider not in PROVIDERS:
            console.print(
                f"[red]run {run_id} was recorded with unknown provider "
                f"'{cassette.provider}' — cannot rebuild the agent to replay it.[/]"
            )
            raise typer.Exit(2)
        prov = PROVIDERS[cassette.provider]
        example = make_example_run(prov, cassette.model or None, api_key="replay-needs-no-key")
        result = do_verify(cassette, example, n=n)

    _print_verdict(result, run_id, len(cassette.boundaries))
    raise typer.Exit(0 if result.passed else 1)


def _print_verdict(result: VerifyResult, run_id: str, n_boundaries: int) -> None:
    """PASS/FAIL banner for humans — numbers come from the verify result, not copy."""
    if result.passed:
        body = (
            f"[bold green]BIT-EXACT[/]  {result.runs}/{result.runs} replays identical\n"
            "network kill-switch on — 0 outbound calls\n"
            f"{n_boundaries} boundaries · "
            f"distinct fingerprints: {result.unique_fingerprints} (expected 1)"
        )
        console.print(Panel(body, title=f"run {run_id}", border_style="green", expand=False))
    else:
        body = f"[bold red]DIVERGED[/] after {result.runs} replay(s)\n{result.detail}"
        console.print(Panel(body, title=f"run {run_id}", border_style="red", expand=False))


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
