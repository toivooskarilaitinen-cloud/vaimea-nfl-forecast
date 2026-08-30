import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import typer

from .backtest import run_backtest
from .data import ingest
from .io import atomic_json
from .monitoring import performance_report
from .operations import (
    approve_forecast,
    create_draft,
    make_review,
    preseason_checklist,
    recovery_audit,
    suggest_starters,
)
from .publish import build_history
from .quality import QualityError, gate_pbp
from .season_history import (
    archive_snapshot,
    audit_history,
    build_public_history,
    run_simulation_snapshot,
)

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


@app.command("archive-season")
def archive_season(
    source: Path = Path("data/season-runs/latest.json"),
    ledger_dir: Path = Path("data/season-forecast-ledger"),
    output: Path = Path("public/data/season-history.json"),
):
    """Append a changed season simulation and rebuild its public history."""
    archived = archive_snapshot(source, ledger_dir)
    payload = build_public_history(ledger_dir, output)
    typer.echo(archived or "no season simulation available")
    typer.echo(f"season snapshots: {len(payload['snapshots'])}")


@app.command("season-run")
def season_run(
    source: Path = Path("data/season-runs/input.json"),
    output: Path = Path("data/season-runs/latest.json"),
):
    """Run 100,000 season simulations from the current approved as-of package."""
    payload = run_simulation_snapshot(source, output)
    typer.echo(output if payload else "no approved season simulation input available")

@app.command()
def backtest(
    season: int = BACKTEST_SEASON,
    output: Path = BACKTEST_OUTPUT,
    cache_dir: Path = BACKTEST_CACHE,
):
    """Replay a completed season with week-level as-of cutoffs."""
    result = run_backtest(season, cache_dir=cache_dir, output=output)
    typer.echo(json.dumps(result["metrics"], indent=2))


@app.command("starter-sheet")
def starter_sheet(
    schedule: Path,
    depth_chart: Path,
    cutoff: str,
    output: Path = Path("data/operator/starter-review.json"),
):
    """Create a human-review sheet from an as-of depth chart."""
    suggestions = suggest_starters(pd.read_csv(schedule), pd.read_csv(depth_chart), cutoff)
    atomic_json(output, {"cutoff": cutoff, "reviewed_by": None, "games": suggestions})
    typer.echo(output)


@app.command("draft")
def draft(
    forecasts: Path,
    quality_report: Path,
    cutoff: str,
    data_fetched_at: str,
    source_week: int,
    output: Path = Path("data/drafts/latest.json"),
    model_version: str = "0.1.1",
    random_seed: int = 20260826,
):
    """Package frozen game probabilities into a reviewable draft."""
    create_draft(
        forecasts,
        quality_report,
        output,
        cutoff,
        data_fetched_at,
        source_week,
        model_version,
        random_seed,
    )
    typer.echo(output)


@app.command("review")
def review(
    draft: Path,
    starters: Path,
    output: Path = Path("public/data/review.json"),
):
    """Run publication gates without writing an official forecast."""
    payload = make_review(
        json.loads(draft.read_text(encoding="utf-8")),
        json.loads(starters.read_text(encoding="utf-8")),
    )
    atomic_json(output, payload)
    typer.echo(json.dumps(payload, indent=2))
    if payload["status"] != "ready":
        raise typer.Exit(1)


@app.command("approve")
def approve(
    draft: Path,
    starters: Path,
    reviewer: str,
    ledger_dir: Path = Path("data/forecast-ledger"),
):
    """Approve one reviewed draft and append it to the immutable ledger."""
    typer.echo(approve_forecast(draft, starters, ledger_dir, reviewer))


@app.command("preseason-check")
def preseason_check(
    previous_ratings: Path,
    starters: Path,
    output: Path = Path("public/data/preseason-status.json"),
):
    """Record the non-model preseason acceptance checklist."""
    payload = preseason_checklist(previous_ratings, starters, output)
    typer.echo(json.dumps(payload, indent=2))
    if payload["status"] == "blocked":
        raise typer.Exit(1)


@app.command("monitor")
def monitor(
    scored_forecasts: Path,
    output: Path = Path("public/data/performance.json"),
    rolling_games: int = 100,
):
    """Publish scoring and calibration monitoring without refitting the model."""
    payload = performance_report(pd.read_csv(scored_forecasts), rolling_games)
    atomic_json(output, payload)
    typer.echo(output)


@app.command("recover")
def recover(
    ledger_dir: Path = Path("data/forecast-ledger"),
    public_dir: Path = Path("public/data"),
):
    """Audit the immutable ledger and rebuild disposable public views."""
    audit = recovery_audit(ledger_dir)
    if audit["status"] != "ok":
        typer.echo(json.dumps(audit, indent=2))
        raise typer.Exit(1)
    season_audit = audit_history(ledger_dir.parent / "season-forecast-ledger")
    if season_audit["status"] != "ok":
        typer.echo(json.dumps(season_audit, indent=2))
        raise typer.Exit(1)
    build_history(ledger_dir, public_dir)
    atomic_json(public_dir / "recovery-audit.json", {**audit, "season_history": season_audit})
    typer.echo(public_dir / "recovery-audit.json")


@app.command("quality-check")
def quality_check(
    clean_dir: Path = Path("data/clean"),
    output: Path = Path("public/data/data-quality.json"),
):
    """Stop publication when the newest clean nflverse snapshot is incomplete."""
    snapshots = sorted(path for path in clean_dir.iterdir() if path.is_dir()) if clean_dir.exists() else []
    if not snapshots:
        raise QualityError("no clean data snapshot found")
    files = sorted(snapshots[-1].glob("pbp_*.parquet"))
    if not files:
        raise QualityError("latest clean snapshot contains no play-by-play files")
    reports = []
    for path in files:
        frame = pd.read_parquet(path)
        report = gate_pbp(frame)
        teams = set(frame.home_team.dropna()) | set(frame.away_team.dropna())
        if report["rows"] < 500:
            raise QualityError(f"{path.name}: unexpectedly few rows: {report['rows']}")
        if len(teams) < 28:
            raise QualityError(f"{path.name}: unexpectedly few teams: {len(teams)}")
        reports.append({
            "file": str(path),
            "season": int(frame.season.max()),
            "latest_week": int(frame.week.max()),
            "teams": len(teams),
            **report,
        })
    payload = {
        "status": "passed",
        "checked_at": datetime.now(UTC).isoformat(),
        "snapshot": snapshots[-1].name,
        "summary": {
            "pbp_rows": sum(report["rows"] for report in reports),
            "games": sum(report["games"] for report in reports),
            "teams": max(report["teams"] for report in reports),
            "qb_coverage": min(report["qb_coverage"] for report in reports),
            "source_week": max(report["latest_week"] for report in reports),
        },
        "files": reports,
    }
    atomic_json(output, payload)
    typer.echo(json.dumps(payload, indent=2))

if __name__ == "__main__": app()
