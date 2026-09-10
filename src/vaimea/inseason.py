from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

import pandas as pd

from .backtest import build_game_features
from .features import game_context, qb_strength, team_strength
from .io import atomic_json
from .model import FEATURES, TEMPERATURE_SLOPE, apply_temperature, fit
from .production import load_games

HISTORY_GAMES = 640


def load_clean_pbp(clean_dir: Path, cutoff: pd.Timestamp) -> pd.DataFrame:
    snapshots = sorted(path for path in clean_dir.iterdir() if path.is_dir())
    if not snapshots:
        raise ValueError("no clean data snapshot found")
    frames = [pd.read_parquet(path) for path in sorted(snapshots[-1].glob("pbp_*.parquet"))]
    if not frames:
        raise ValueError("latest clean snapshot has no play-by-play files")
    pbp = pd.concat(frames, ignore_index=True)
    pbp["game_date"] = pd.to_datetime(pbp.game_date)
    available = pd.to_datetime(pbp.available_at, utc=True)
    return pbp.loc[available <= cutoff].sort_values(["game_date", "game_id"]).reset_index(drop=True)


def _starter_map(review: dict) -> dict[str, dict]:
    return {row["team"]: row for row in review.get("teams", [])}


def _selected_qb(starters: dict[str, dict], team: str, live_qb_id: str | None) -> str | None:
    reviewed = starters.get(team, {})
    if reviewed.get("manual_override") is True:
        return reviewed.get("player_id")
    return live_qb_id or reviewed.get("player_id")


def _rating(tables: pd.DataFrame, team: str) -> float:
    if team not in tables.index:
        return 0.0
    return float(tables.loc[team, ["offense_epa_adj", "defense_epa_adj"]].sum())


def _qb_rating(qbs: pd.DataFrame, player_id: str | None) -> float:
    if not player_id or player_id not in qbs.index:
        return 0.0
    value = qbs.loc[player_id, "qb_rating"]
    return float(value.iloc[0] if hasattr(value, "iloc") else value)


def update_season_input(
    clean_dir: Path = Path("data/clean"),
    input_path: Path = Path("data/season-runs/input.json"),
    review_path: Path = Path("data/operator/preseason-qb-review.json"),
    ratings_path: Path = Path("public/data/team-ratings.json"),
    now: pd.Timestamp | None = None,
    games: pd.DataFrame | None = None,
) -> dict:
    now = now or pd.Timestamp.now(tz="UTC")
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    base = json.loads(input_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    season = int(base["season"])
    pbp = load_clean_pbp(clean_dir, now)
    schedule = (games if games is not None else load_games()).copy()
    schedule["gameday"] = pd.to_datetime(schedule.gameday)

    # The model is fitted only on completed 2021-2025 games. Current-season rows
    # update the features below but never the frozen model coefficients.
    historical_schedule = schedule[schedule.season.between(2021, season - 1)]
    historical_pbp = pbp[pbp.season < season]
    training = build_game_features(
        historical_schedule, historical_pbp, list(range(2021, season))
    )
    if len(training) < 100:
        raise ValueError("frozen model needs at least 100 historical games")
    model = fit(training)

    recent_ids = pbp[["game_id", "game_date"]].drop_duplicates().tail(HISTORY_GAMES).game_id
    recent = pbp[pbp.game_id.isin(recent_ids)]
    teams = team_strength(recent).set_index("team")
    qbs = qb_strength(recent).set_index("passer_player_id")
    starters = _starter_map(review)

    current = schedule[(schedule.season == season) & schedule.game_type.eq("REG")].copy()
    current = current.sort_values(["week", "gameday", "gametime", "game_id"])
    context = game_context(current).set_index("game_id")
    rows = []
    for game in current.itertuples():
        home_live = None if pd.isna(getattr(game, "home_qb_id", None)) else str(game.home_qb_id)
        away_live = None if pd.isna(getattr(game, "away_qb_id", None)) else str(game.away_qb_id)
        home_qb_id = _selected_qb(starters, game.home_team, home_live)
        away_qb_id = _selected_qb(starters, game.away_team, away_live)
        home_score = getattr(game, "home_score", None)
        away_score = getattr(game, "away_score", None)
        completed = pd.notna(home_score) and pd.notna(away_score) and home_score != away_score
        if completed:
            probability = float(home_score > away_score)
        else:
            ctx = context.loc[game.game_id]
            features = pd.DataFrame([{
                "strength_diff": _rating(teams, game.home_team) - _rating(teams, game.away_team),
                "qb_diff": _qb_rating(qbs, home_qb_id) - _qb_rating(qbs, away_qb_id),
                "home_field": float(ctx.home_field),
                "rest_diff": float(ctx.rest_diff),
            }])
            probability = float(
                apply_temperature(model.predict_proba(features[FEATURES])[:, 1], TEMPERATURE_SLOPE)[0]
            )
        rows.append({
            "game_id": game.game_id, "week": int(game.week),
            "gameday": str(pd.Timestamp(game.gameday).date()),
            "away_team": game.away_team, "home_team": game.home_team,
            "home_win_probability": probability,
            "probability_home_qb_id": home_qb_id,
            "probability_away_qb_id": away_qb_id,
            "completed": bool(completed),
        })

    playoff_rows = []
    all_teams = sorted(starters)
    for home_team in all_teams:
        for away_team in all_teams:
            if home_team == away_team:
                continue
            common = {
                "strength_diff": _rating(teams, home_team) - _rating(teams, away_team),
                "qb_diff": _qb_rating(qbs, starters[home_team].get("player_id"))
                - _qb_rating(qbs, starters[away_team].get("player_id")),
            }
            contexts = pd.DataFrame([
                {**common, "home_field": 1.0, "rest_diff": 0.0},
                {**common, "home_field": 1.0, "rest_diff": 7.0},
                {**common, "home_field": 0.0, "rest_diff": 0.0},
            ])
            probabilities = apply_temperature(
                model.predict_proba(contexts[FEATURES])[:, 1], TEMPERATURE_SLOPE
            )
            playoff_rows.append({
                "home_team": home_team, "away_team": away_team,
                "home_win_probability": float(probabilities[0]),
                "bye_home_win_probability": float(probabilities[1]),
                "neutral_win_probability": float(probabilities[2]),
            })

    ratings = []
    for team in all_teams:
        offense = float(teams.loc[team, "offense_epa_adj"]) if team in teams.index else 0.0
        defense = float(teams.loc[team, "defense_epa_adj"]) if team in teams.index else 0.0
        qb = _qb_rating(qbs, starters[team].get("player_id"))
        ratings.append({"team": team, "offense": offense, "defense": defense, "qb": qb,
                        "overall": offense + defense + qb})
    ratings.sort(key=lambda row: row["overall"], reverse=True)
    stamp = now.to_pydatetime().astimezone(UTC).replace(microsecond=0).isoformat()
    payload = {**base, "week": int(current.loc[current.gameday <= now.tz_localize(None), "week"].max())
               if (current.gameday <= now.tz_localize(None)).any() else "PRE",
               "as_of": stamp, "schedule": rows, "playoff_matchups": playoff_rows}
    payload["provenance"] = {**payload.get("provenance", {}),
        "training_seasons": list(range(2021, season)),
        "feature_history_seasons": sorted(int(value) for value in pbp.season.unique()),
        "current_season_updates": True, "available_at_cutoff": stamp,
        "training_games": len(training)}
    atomic_json(input_path, payload)
    atomic_json(ratings_path, {"season": season, "as_of": stamp, "ratings": ratings})
    return payload
