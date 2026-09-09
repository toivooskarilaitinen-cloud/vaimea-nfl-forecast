from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import requests

from .io import atomic_json, sha256
from .quality import QualityError

NFLDATA_GAMES_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
DEFAULT_FINAL_LOCK_MINUTES = 90


def _object_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_iso(value: pd.Timestamp) -> str:
    value = value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")
    return value.isoformat()


def load_games(url: str = NFLDATA_GAMES_URL, timeout: int = 60) -> pd.DataFrame:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    from io import StringIO

    return pd.read_csv(StringIO(response.text), low_memory=False)


def _kickoff_utc(row: pd.Series) -> pd.Timestamp:
    if pd.isna(row.get("gameday")) or pd.isna(row.get("gametime")):
        raise QualityError(f"{row.get('game_id')}: missing gameday/gametime")
    eastern = pd.Timestamp(f"{row.gameday} {row.gametime}", tz="America/New_York")
    return eastern.tz_convert("UTC")


def _probability_qbs(preseason_review: dict) -> dict[str, dict]:
    result = {}
    for row in preseason_review.get("teams", []):
        if row.get("team"):
            result[row["team"]] = row
    return result


def _latest_official_by_game(ledger_dir: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for path in sorted(ledger_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        stamp = payload.get("approved_at") or payload.get("cutoff")
        for row in payload.get("forecasts", []):
            enriched = {**row, "_snapshot_at": stamp}
            previous = latest.get(row["game_id"])
            if previous is None or str(stamp) > str(previous.get("_snapshot_at")):
                latest[row["game_id"]] = enriched
    return latest


def prepare_review_package(
    season_input: dict,
    games: pd.DataFrame,
    quality: dict,
    preseason_review: dict,
    ledger_dir: Path,
    now: pd.Timestamp | None = None,
    final_lock_minutes: int = DEFAULT_FINAL_LOCK_MINUTES,
) -> tuple[dict, dict, dict]:
    now = now or pd.Timestamp.now(tz="UTC")
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    if final_lock_minutes < 1:
        raise QualityError("final_lock_minutes must be positive")

    source_schedule = pd.DataFrame(season_input.get("schedule", []))
    if source_schedule.empty:
        raise QualityError("season forecast input has no schedule")
    live = games[(games.season == int(season_input["season"])) & games.game_type.eq("REG")].copy()
    if live.empty:
        raise QualityError("current schedule source has no regular-season games")
    live = live.set_index("game_id", drop=False)

    rows = []
    for base in source_schedule.to_dict("records"):
        game_id = base["game_id"]
        if game_id not in live.index:
            continue
        current = live.loc[game_id]
        kickoff = _kickoff_utc(current)
        final_lock_at = kickoff - pd.Timedelta(minutes=final_lock_minutes)
        if now >= final_lock_at:
            continue
        rows.append((base, current, kickoff, final_lock_at))

    if not rows:
        request = {
            "kind": "qb_review_request",
            "status": "nothing_to_review",
            "review_needed": False,
            "generated_at": _utc_iso(now),
            "games": [],
        }
        return {}, {}, request

    target_week = min(int(base["week"]) for base, *_ in rows)
    rows = [item for item in rows if int(item[0]["week"]) == target_week]
    probability_qbs = _probability_qbs(preseason_review)
    existing = _latest_official_by_game(ledger_dir)
    forecast_rows = []
    approvals = {}

    for base, current, kickoff, final_lock_at in rows:
        home_team, away_team = base["home_team"], base["away_team"]
        probability_home = probability_qbs.get(home_team, {})
        probability_away = probability_qbs.get(away_team, {})
        row = {
            **base,
            "kickoff": _utc_iso(kickoff),
            "final_lock_at": _utc_iso(final_lock_at),
            "neutral_site": str(current.get("location", "")).lower() == "neutral",
            "home_qb_id": None if pd.isna(current.get("home_qb_id")) else str(current.get("home_qb_id")),
            "away_qb_id": None if pd.isna(current.get("away_qb_id")) else str(current.get("away_qb_id")),
            "home_qb_name": None if pd.isna(current.get("home_qb_name")) else str(current.get("home_qb_name")),
            "away_qb_name": None if pd.isna(current.get("away_qb_name")) else str(current.get("away_qb_name")),
            "probability_home_qb_id": probability_home.get("player_id"),
            "probability_away_qb_id": probability_away.get("player_id"),
            "change_reason": "scheduled_production_snapshot",
        }
        prior = existing.get(base["game_id"])
        changed = prior is None or any(
            prior.get(key) != row.get(key)
            for key in ("home_win_probability", "home_qb_id", "away_qb_id")
        )
        if not changed:
            continue
        forecast_rows.append(row)
        approvals[base["game_id"]] = {
            "home_qb_id": row["home_qb_id"],
            "away_qb_id": row["away_qb_id"],
            "home_qb_name": row["home_qb_name"],
            "away_qb_name": row["away_qb_name"],
            "home_source": "nflverse_nfldata_games",
            "away_source": "nflverse_nfldata_games",
            "approved": False,
            "status": "needs_review",
        }

    if not forecast_rows:
        request = {
            "kind": "qb_review_request",
            "status": "up_to_date",
            "review_needed": False,
            "generated_at": _utc_iso(now),
            "source_week": target_week,
            "games": [],
        }
        return {}, {}, request

    quality_summary = dict(quality.get("summary", {}))
    quality_summary["qb_coverage"] = sum(
        bool(row.get(field))
        for row in forecast_rows
        for field in ("home_qb_id", "away_qb_id")
    ) / max(2 * len(forecast_rows), 1)
    cutoff = _utc_iso(now)
    draft = {
        "kind": "forecast_draft",
        "status": "needs_review",
        "model_version": season_input["model_version"],
        "cutoff": cutoff,
        "data_fetched_at": quality.get("checked_at", cutoff),
        "source_week": target_week,
        "random_seed": season_input.get("random_seed"),
        "tiebreaker_mode": season_input.get("tiebreaker_mode", "approximation_v0.1"),
        "data_quality": quality_summary,
        "input_hashes": {
            "season_forecast_input": _object_sha256(season_input),
            "schedule_rows": _object_sha256(
                live.reset_index(drop=True)[
                    [
                        "game_id", "gameday", "gametime", "away_team", "home_team",
                        "away_qb_id", "home_qb_id", "away_qb_name", "home_qb_name", "location"
                    ]
                ].fillna("").to_dict("records")
            ),
            "schedule_source": NFLDATA_GAMES_URL,
        },
        "forecasts": forecast_rows,
    }
    starter_review = {
        "kind": "starter_review",
        "status": "needs_review",
        "cutoff": cutoff,
        "source_week": target_week,
        "reviewed_by": None,
        "reviewed_at": None,
        "games": approvals,
    }
    request_games = [
        {
            "game_id": row["game_id"],
            "away_team": row["away_team"],
            "home_team": row["home_team"],
            "away_qb_name": row["away_qb_name"],
            "home_qb_name": row["home_qb_name"],
            "home_win_probability": row["home_win_probability"],
            "final_lock_at": row["final_lock_at"],
            "qb_probability_match": row["home_qb_id"] == row["probability_home_qb_id"]
            and row["away_qb_id"] == row["probability_away_qb_id"],
        }
        for row in forecast_rows
    ]
    request = {
        "kind": "qb_review_request",
        "status": "needs_review",
        "review_needed": True,
        "generated_at": cutoff,
        "source_week": target_week,
        "approval_deadline": min(row["final_lock_at"] for row in forecast_rows),
        "games": request_games,
    }
    return draft, starter_review, request


def write_review_package(
    season_input_path: Path = Path("data/season-runs/input.json"),
    quality_path: Path = Path("public/data/data-quality.json"),
    preseason_review_path: Path = Path("data/operator/preseason-qb-review.json"),
    ledger_dir: Path = Path("data/forecast-ledger"),
    draft_path: Path = Path("data/drafts/latest.json"),
    starters_path: Path = Path("data/operator/starter-review.json"),
    request_path: Path = Path("public/data/review-request.json"),
    final_lock_minutes: int = DEFAULT_FINAL_LOCK_MINUTES,
) -> dict:
    season_input = json.loads(season_input_path.read_text(encoding="utf-8"))
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    preseason_review = json.loads(preseason_review_path.read_text(encoding="utf-8"))
    games = load_games()
    draft, starters, request = prepare_review_package(
        season_input,
        games,
        quality,
        preseason_review,
        ledger_dir,
        final_lock_minutes=final_lock_minutes,
    )
    if draft:
        atomic_json(draft_path, draft)
        # bind the human-review sheet to the exact generated draft
        starters["draft_sha256"] = sha256(draft_path)
        atomic_json(starters_path, starters)
    atomic_json(request_path, request)
    return request
