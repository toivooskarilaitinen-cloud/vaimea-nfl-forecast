from __future__ import annotations

import json
import os
import platform
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from .io import atomic_json, sha256
from .quality import QualityError


def _utc(value: str) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def create_draft(
    forecasts_path: Path,
    quality_path: Path,
    output: Path,
    cutoff: str,
    data_fetched_at: str,
    source_week: int,
    model_version: str,
    random_seed: int,
) -> dict:
    """Package already-computed probabilities for review without changing them."""
    forecasts = pd.read_csv(forecasts_path).to_dict("records")
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    quality_summary = dict(quality.get("summary", {}))
    qb_fields = [row.get(field) for row in forecasts for field in ("home_qb_id", "away_qb_id")]
    quality_summary["qb_coverage"] = sum(bool(value) for value in qb_fields) / max(len(qb_fields), 1)
    payload = {
        "kind": "forecast_draft",
        "status": "needs_review",
        "model_version": model_version,
        "cutoff": cutoff,
        "data_fetched_at": data_fetched_at,
        "source_week": source_week,
        "random_seed": random_seed,
        "tiebreaker_mode": "approximation_v0.1",
        "data_quality": quality_summary,
        "input_hashes": {
            "forecasts": sha256(forecasts_path),
            "quality_report": sha256(quality_path),
        },
        "forecasts": forecasts,
    }
    atomic_json(output, payload)
    return payload


def suggest_starters(schedule: pd.DataFrame, depth_chart: pd.DataFrame, cutoff: str) -> dict:
    """Suggest QB1 from an as-of depth chart; never infer from future snaps."""
    required = {"team", "player_id", "position", "depth_order", "available_at"}
    missing = required - set(depth_chart.columns)
    if missing:
        raise QualityError(f"depth chart missing columns: {sorted(missing)}")
    cutoff_at = _utc(cutoff)
    chart = depth_chart.copy()
    chart["available_at"] = pd.to_datetime(chart.available_at, utc=True)
    chart = chart[(chart.available_at < cutoff_at) & (chart.position == "QB")]
    chart = chart.sort_values(["team", "depth_order", "available_at"], ascending=[True, True, False])
    qb1 = chart.drop_duplicates("team").set_index("team")
    if "game_id" not in schedule:
        raise QualityError("schedule missing game_id")
    games = {}
    for game in schedule.itertuples():
        home_id = None if game.home_team not in qb1.index else str(qb1.loc[game.home_team, "player_id"])
        away_id = None if game.away_team not in qb1.index else str(qb1.loc[game.away_team, "player_id"])
        games[game.game_id] = {
            "home_qb_id": home_id,
            "away_qb_id": away_id,
            "home_source": "nflverse_depth_chart" if home_id else None,
            "away_source": "nflverse_depth_chart" if away_id else None,
            "approved": False,
            "status": "needs_review",
        }
    return games


def make_review(draft: dict, starter_approvals: dict, max_age_hours: int = 72) -> dict:
    forecasts = draft.get("forecasts", [])
    if not forecasts:
        raise QualityError("forecast draft is empty")
    now = pd.Timestamp.now(tz="UTC")
    cutoff = _utc(draft["cutoff"])
    fetched = _utc(draft["data_fetched_at"])
    errors: list[str] = []
    warnings: list[str] = []
    game_ids = [row.get("game_id") for row in forecasts]
    if len(game_ids) != len(set(game_ids)):
        errors.append("duplicate game_id")
    if not 1 <= len(forecasts) <= 16:
        errors.append(f"unexpected weekly game count: {len(forecasts)}")
    age_hours = (now - fetched).total_seconds() / 3600
    if age_hours > max_age_hours:
        errors.append(f"data is stale: {age_hours:.1f} hours")
    if fetched > now + pd.Timedelta(minutes=5):
        errors.append("data_fetched_at is in the future")
    data_quality = draft.get("data_quality", {})
    for field in ("pbp_rows", "games", "teams", "qb_coverage"):
        if field not in data_quality:
            errors.append(f"data_quality.{field} is missing")
    if data_quality.get("pbp_rows", 0) < 500:
        errors.append("data_quality.pbp_rows is unexpectedly low")
    if data_quality.get("teams", 0) < 28:
        errors.append("data_quality.teams is unexpectedly low")
    if data_quality.get("qb_coverage", 0) < 1:
        errors.append("data_quality.qb_coverage is incomplete")

    approvals = starter_approvals.get("games", {})
    reviewed_games = []
    for row in forecasts:
        game_id = row.get("game_id")
        probability = row.get("home_win_probability")
        try:
            probability = float(probability)
        except (TypeError, ValueError):
            errors.append(f"{game_id}: invalid probability")
            probability = 0.5
        if not 0 <= probability <= 1:
            errors.append(f"{game_id}: probability outside [0,1]")
        if cutoff >= _utc(row["kickoff"]):
            errors.append(f"{game_id}: cutoff does not precede kickoff")
        if row.get("home_team") == row.get("away_team"):
            errors.append(f"{game_id}: identical teams")
        approval = approvals.get(game_id, {})
        for side in ("home", "away"):
            proposed = row.get(f"{side}_qb_id")
            accepted = approval.get(f"{side}_qb_id")
            if not proposed:
                errors.append(f"{game_id}: missing proposed {side} QB")
            if accepted != proposed:
                errors.append(f"{game_id}: {side} QB is not approved")
        if approval.get("approved") is not True:
            errors.append(f"{game_id}: starter review is not approved")
        row_warnings = list(row.get("warnings", []))
        if row.get("neutral_site"):
            row_warnings.append("neutral_site_home_field_zero")
        if draft.get("tiebreaker_mode") != "official_complete":
            row_warnings.append("tiebreaker_approximation")
        warnings.extend(f"{game_id}: {item}" for item in row_warnings)
        reviewed_games.append({**row, "warnings": sorted(set(row_warnings))})

    input_hashes = draft.get("input_hashes", {})
    if not input_hashes:
        errors.append("input_hashes are missing")
    return {
        "status": "ready" if not errors else "blocked",
        "checked_at": datetime.now(UTC).isoformat(),
        "data_age_hours": round(age_hours, 2),
        "source_week": draft.get("source_week"),
        "games": reviewed_games,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
    }


def approve_forecast(
    draft_path: Path,
    approvals_path: Path,
    ledger_dir: Path,
    reviewer: str,
    config_path: Path = Path("config/model.yaml"),
) -> Path:
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
    review = make_review(draft, approvals)
    if review["status"] != "ready":
        raise QualityError("forecast approval blocked: " + "; ".join(review["errors"]))
    cutoff = draft["cutoff"]
    model_version = draft["model_version"]
    filename = f"{cutoff.replace(':', '-')}_{model_version}.json"
    target = ledger_dir / filename
    if target.exists():
        raise FileExistsError(f"forecast ledger is append-only: {target}")
    payload = {
        **draft,
        "status": "official",
        "approved_by": reviewer,
        "approved_at": datetime.now(UTC).isoformat(),
        "forecasts": review["games"],
        "quality": {key: review[key] for key in ("checked_at", "data_age_hours", "errors", "warnings")},
        "reproducibility": {
            "draft_sha256": sha256(draft_path),
            "approvals_sha256": sha256(approvals_path),
            "config_sha256": sha256(config_path),
            "git_commit": os.environ.get("GITHUB_SHA", "local-uncommitted"),
            "python": platform.python_version(),
            "random_seed": draft.get("random_seed"),
        },
    }
    atomic_json(target, payload)
    return target


def preseason_checklist(previous_ratings: Path, starters: Path, output: Path) -> dict:
    checks = {
        "previous_season_ratings_present": previous_ratings.exists(),
        "starter_review_present": starters.exists(),
        "model_and_calibration_frozen": True,
        "injury_automation_disabled": True,
        "market_data_not_used_as_feature": True,
    }
    payload = {
        "kind": "preseason_acceptance",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "ready_for_human_review" if all(checks.values()) else "blocked",
        "checks": checks,
        "note": "Team-strength carryover is not re-estimated here; the frozen production process must supply it.",
    }
    atomic_json(output, payload)
    return payload


def recovery_audit(ledger_dir: Path) -> dict:
    files = sorted(ledger_dir.glob("*.json"))
    seen: set[tuple[str, str, str]] = set()
    errors = []
    hashes = {}
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        hashes[path.name] = sha256(path)
        for row in payload.get("forecasts", []):
            key = (row["game_id"], payload["model_version"], payload["cutoff"])
            if key in seen:
                errors.append(f"duplicate official forecast: {key}")
            seen.add(key)
    return {"status": "ok" if not errors else "failed", "files": len(files), "hashes": hashes, "errors": errors}
