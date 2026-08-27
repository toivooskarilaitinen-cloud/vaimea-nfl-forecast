import json
from pathlib import Path

import typer

from .backtest import run_backtest
from .data import ingest
from .publish import build_history

app=typer.Typer(no_args_is_help=True)
SEASONS = typer.Option(..., help="NFL season; repeat the option to fetch several")
BACKTEST_SEASON = typer.Option(2025, help="Completed NFL season to replay")
BACKTEST_OUTPUT = typer.Option(Path("public/data/backtest-2025.json"))
BACKTEST_CACHE = typer.Option(Path("data/backtest-cache"))

@app.command()
def download(season: list[int] = SEASONS, data_dir: Path = Path("data")):
    """Create an immutable nflverse snapshot and cleaned layer."""
    for p in ingest(data_dir,season): typer.echo(p)

@app.command()
def publish(ledger_dir: Path=Path("data/forecast-ledger"), public_dir: Path=Path("public/data")):
    """Build latest, movers and history JSON."""
    build_history(ledger_dir,public_dir)

@app.command()
def backtest(
    season: int = BACKTEST_SEASON,
    output: Path = BACKTEST_OUTPUT,
    cache_dir: Path = BACKTEST_CACHE,
):
    """Replay a completed season with week-level as-of cutoffs."""
    result = run_backtest(season, cache_dir=cache_dir, output=output)
    typer.echo(json.dumps(result["metrics"], indent=2))

if __name__ == "__main__": app()
