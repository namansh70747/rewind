"""The ``fr`` command-line interface — the Phase-0 walking-skeleton surface.

    fr record --provider nvidia          # record the example agent -> a run id
    fr show <run_id>                     # scrub the decision timeline
    fr verify <run_id> --n 50            # replay bit-exact, offline, zero API calls
    fr runs                              # list recorded runs

The API key is read from the environment or a git-ignored ``.env`` file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from .example_agent import make_example_run
from .providers import OPENAI, PROVIDERS
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
    if kind == "http" and isinstance(response, dict):
        body = response.get("body", {})
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            try:
                text = body["content"][0]["text"]
            except (KeyError, IndexError, TypeError):
                text = str(body)
        text = " ".join(str(text).split())
        return f"[{response.get('status', '?')}] {text[:70]}"
    return str(response)


@app.command()
def record(
    provider: Annotated[str, typer.Option(help="openai | nvidia | anthropic")] = "openai",
    model: Annotated[str | None, typer.Option(help="override the provider's default model")] = None,
    db: Annotated[str, typer.Option(help="path to the run store")] = DEFAULT_DB,
) -> None:
    """Record one live run of the bundled example agent."""
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

    prov = PROVIDERS.get(cassette.provider, OPENAI)
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


if __name__ == "__main__":
    app()
