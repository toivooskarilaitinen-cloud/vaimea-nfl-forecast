from __future__ import annotations

import json
import os
import platform
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from .io import atomic_json, sha256
from .quality import QualityError

DEFAULT_FINAL_LOCK_MINUTES = 90


def _utc(value: str) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _final_lock(row: dict, minutes: int = DEFAULT_FINAL_LOCK_MINUTES) -> pd.Timestamp:
    explicit = row.get("final_lock_at")
    if explicit:
        return _utc(explicit)
    return _utc(row["kickoff"]) - pd.Timedelta(minutes=minutes)


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


def confirm_starters(starter_approvals: dict, reviewer: str, confirmation: str) -> dict:
    """Turn one generated starter sheet into an explicit human approval."""
    if confirmation.strip().upper() != "APPROVE":
        raise QualityError("QB confirmation must be exactly APPROVE")
    if not reviewer.strip():
        raise QualityError("reviewer is required")
    games = starter_approvals.get("games", {})
    if not games:
        raise QualityError("starter review has no games")
    approved_at = datetime.now(UTC).isoformat()
    for game in games.values():
        game["approved"] = True
        game["status"] = "approved"
    starter_approvals["reviewed_by"] = reviewer.strip()
    starter_approvals["reviewed_at"] = approved_at
    starter_approvals["status"] = "approved"
    return starter_approvals


def set_qb_override(
    review_path: Path,
    team: str,
    player_id: str,
    player_name: str,
    reviewer: str,
    confirmation: str,
) -> dict:
    """Record a human-supplied QB that must drive the next recomputation."""
    if confirmation.strip().upper() != "RECOMPUTE":
        raise QualityError("QB override confirmation must be exactly RECOMPUTE")
    values = (team.strip().upper(), player_id.strip(), player_name.strip(), reviewer.strip())
    if not all(values):
        raise QualityError("team, player id, player name and reviewer are required")
    payload = json.loads(review_path.read_text(encoding="utf-8"))
    row = next((item for item in payload.get("teams", []) if item.get("team") == values[0]), None)
    if row is None:
        raise QualityError(f"unknown team: {values[0]}")
    changed_at = datetime.now(UTC).isoformat()
    row.update(
        {
            "player_id": values[1],
            "player_name": values[2],
            "approved": True,
            "manual_override": True,
            "override_reviewed_by": values[3],
            "override_at": changed_at,
        }
    )
    payload["last_manual_override_at"] = changed_at
    atomic_json(review_path, payload)
    return row


def make_review(
    draft: dict,
    starter_approvals: dict,
    max_age_hours: int = 72,
    now: pd.Timestamp | None = None,
) -> dict:
    forecasts = draft.get("forecasts", [])
    if not forecasts:
        raise QualityError("forecast draft is empty")
    now = now or pd.Timestamp.now(tz="UTC")
    now = _utc(str(now))
    cutoff = _utc(draft["cutoff"])
    fetched = _utc(draft["data_fetched_at"])
    errors: list[str] = []
    warnings: list[str] = []

    if starter_approvals.get("kind") == "starter_review":
        if starter_approvals.get("cutoff") != draft.get("cutoff"):
            errors.append("starter review cutoff does not match draft cutoff")
        if starter_approvals.get("source_week") != draft.get("source_week"):
            errors.append("starter review source_week does not match draft")

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
        kickoff = _utc(row["kickoff"])
        final_lock_at = _final_lock(row)
        if cutoff >= kickoff:
            errors.append(f"{game_id}: cutoff does not precede kickoff")
        if final_lock_at >= kickoff:
            errors.append(f"{game_id}: final lock must precede kickoff")
        if now >= final_lock_at:
            errors.append(f"{game_id}: final lock has passed")
        if row.get("home_team") == row.get("away_team"):
            errors.append(f"{game_id}: identical teams")

        probability_home_qb = row.get("probability_home_qb_id", row.get("home_qb_id"))
        probability_away_qb = row.get("probability_away_qb_id", row.get("away_qb_id"))
        if probability_home_qb != row.get("home_qb_id"):
            errors.append(f"{game_id}: home QB changed; probability must be recomputed")
        if probability_away_qb != row.get("away_qb_id"):
            errors.append(f"{game_id}: away QB changed; probability must be recomputed")

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
        reviewed_games.append({**row, "final_lock_at": final_lock_at.isoformat(), "warnings": sorted(set(row_warnings))})

    input_hashes = draft.get("input_hashes", {})
    if not input_hashes:
        errors.append("input_hashes are missing")
    return {
        "status": "ready" if not errors else "blocked",
        "checked_at": now.isoformat(),
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
    approved_at = pd.Timestamp.now(tz="UTC")
    review = make_review(draft, approvals, now=approved_at)
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
        "approved_at": approved_at.isoformat(),
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
