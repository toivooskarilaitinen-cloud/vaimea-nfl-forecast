from pathlib import Path

import typer

from .data import ingest
from .publish import build_history

app=typer.Typer(no_args_is_help=True)
SEASONS = typer.Option(..., help="NFL season; repeat the option to fetch several")

@app.command()
def download(season: list[int] = SEASONS, data_dir: Path = Path("data")):
    """Create an immutable nflverse snapshot and cleaned layer."""
    for p in ingest(data_dir,season): typer.echo(p)

@app.command()
def publish(ledger_dir: Path=Path("data/forecast-ledger"), public_dir: Path=Path("public/data")):
    """Build latest, movers and history JSON."""
    build_history(ledger_dir,public_dir)

if __name__ == "__main__": app()
