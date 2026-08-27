from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .features import game_context, qb_strength, team_strength
from .model import FEATURES, _brier, _log_loss, fit

SCHEDULE_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet"
)
PBP_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/pbp/"
    "play_by_play_{season}.parquet"
)


def _read_parquet(url: str, cache_path: Path) -> pd.DataFrame:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if not cache_path.exists():
        import requests

        response = requests.get(url, timeout=180)
        response.raise_for_status()
        temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
        temporary.write_bytes(response.content)
        temporary.replace(cache_path)
    return pd.read_parquet(cache_path)


def load_backtest_data(cache_dir: Path, seasons: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    schedule = _read_parquet(SCHEDULE_URL, cache_dir / "schedules.parquet")
    schedule = schedule[schedule.season.isin(seasons)].copy()
    schedule["gameday"] = pd.to_datetime(schedule.gameday)

    wanted = [
        "game_id", "season", "week", "game_date", "home_team", "away_team",
        "posteam", "defteam", "epa", "cpoe", "qb_dropback", "passer_player_id",
        "passer_player_name",
    ]
    frames = []
    for season in seasons:
        frame = _read_parquet(PBP_URL.format(season=season), cache_dir / f"pbp_{season}.parquet")
        frames.append(frame[[column for column in wanted if column in frame]].copy())
    pbp = pd.concat(frames, ignore_index=True)
    pbp["game_date"] = pd.to_datetime(pbp.game_date)
    pbp = pbp.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    return schedule, pbp


def _starter_proxy(history: pd.DataFrame) -> dict[str, str]:
    dropbacks = history[(history.qb_dropback == 1) & history.passer_player_id.notna()].copy()
    if dropbacks.empty:
        return {}
    recent_games = (
        dropbacks.groupby("posteam", as_index=False)["game_date"].max()
        .rename(columns={"game_date": "last_game"})
    )
    recent = dropbacks.merge(recent_games, on="posteam")
    recent = recent[recent.game_date == recent.last_game]
    counts = recent.groupby(["posteam", "passer_player_id"]).size().rename("n").reset_index()
    return (
        counts.sort_values(["posteam", "n"], ascending=[True, False])
        .drop_duplicates("posteam")
        .set_index("posteam")["passer_player_id"]
        .to_dict()
    )


def build_game_features(
    schedule: pd.DataFrame,
    pbp: pd.DataFrame,
    feature_seasons: list[int],
    history_games: int = 640,
) -> pd.DataFrame:
    games = schedule[
        schedule.season.isin(feature_seasons)
        & schedule.game_type.ne("PRE")
        & schedule.home_score.notna()
        & schedule.away_score.notna()
        & schedule.home_score.ne(schedule.away_score)
    ].sort_values(["gameday", "gametime", "game_id"])
    context = game_context(schedule.sort_values(["gameday", "gametime"]))
    context_by_game = context.set_index("game_id")
    rows: list[dict] = []

    for (season, week), week_games in games.groupby(["season", "week"], sort=True):
        cutoff = week_games.gameday.min()
        history = pbp[pbp.game_date < cutoff]
        recent_ids = history[["game_id", "game_date"]].drop_duplicates().tail(history_games).game_id
        history = history[history.game_id.isin(recent_ids)]
        teams = team_strength(history).set_index("team")
        quarterbacks = (
            qb_strength(history)
            .groupby("passer_player_id", as_index=True)
            .agg(qb_rating=("qb_rating", "mean"))
        )
        starters = _starter_proxy(history)

        for game in week_games.itertuples():
            ctx = context_by_game.loc[game.game_id]
            home_strength = (
                float(teams.loc[game.home_team, ["offense_epa_adj", "defense_epa_adj"]].sum())
                if game.home_team in teams.index
                else 0.0
            )
            away_strength = (
                float(teams.loc[game.away_team, ["offense_epa_adj", "defense_epa_adj"]].sum())
                if game.away_team in teams.index
                else 0.0
            )
            home_passer = starters.get(game.home_team)
            away_passer = starters.get(game.away_team)
            home_qb = (
                float(quarterbacks.loc[home_passer, "qb_rating"])
                if home_passer in quarterbacks.index
                else 0.0
            )
            away_qb = (
                float(quarterbacks.loc[away_passer, "qb_rating"])
                if away_passer in quarterbacks.index
                else 0.0
            )
            rows.append(
                {
                    "game_id": game.game_id,
                    "season": int(season),
                    "week": int(week),
                    "gameday": game.gameday.date().isoformat(),
                    "away_team": game.away_team,
                    "home_team": game.home_team,
                    "away_score": int(game.away_score),
                    "home_score": int(game.home_score),
                    "home_win": int(game.home_score > game.away_score),
                    "strength_diff": home_strength - away_strength,
                    "qb_diff": home_qb - away_qb,
                    "home_field": float(ctx.home_field),
                    "rest_diff": float(ctx.rest_diff),
                }
            )
    return pd.DataFrame(rows)


def _calibration(rows: pd.DataFrame) -> list[dict]:
    bins = pd.cut(rows.probability, np.linspace(0, 1, 11), include_lowest=True)
    grouped = (
        rows.assign(bin=bins)
        .groupby("bin", observed=True)
        .agg(n=("home_win", "size"), predicted=("probability", "mean"), observed=("home_win", "mean"))
        .reset_index()
    )
    grouped["bin"] = grouped["bin"].astype(str)
    return grouped.to_dict("records")


def run_backtest(
    target_season: int,
    cache_dir: Path = Path("data/backtest-cache"),
    output: Path | None = None,
    history_start: int = 2018,
    first_feature_season: int = 2021,
) -> dict:
    seasons = list(range(history_start, target_season + 1))
    schedule, pbp = load_backtest_data(cache_dir, seasons)
    features = build_game_features(
        schedule,
        pbp,
        list(range(first_feature_season, target_season + 1)),
    )
    train = features[features.season < target_season]
    test = features[features.season == target_season].copy()
    if len(train) < 100 or test.empty:
        raise ValueError("Backtest needs at least 100 prior games and a non-empty target season")

    model = fit(train)
    test["probability"] = model.predict_proba(test[FEATURES])[:, 1]
    y = test.home_win.to_numpy()
    probability = test.probability.to_numpy()
    historical_home_rate = float(train.home_win.mean())
    baseline = np.repeat(historical_home_rate, len(test))
    weekly = []
    for week, group in test.groupby("week"):
        weekly.append(
            {
                "week": int(week),
                "games": len(group),
                "brier": _brier(group.home_win, group.probability),
                "accuracy": float(((group.probability >= 0.5) == group.home_win).mean()),
            }
        )

    result = {
        "kind": "historical_backtest",
        "official_forecast_ledger": False,
        "season": target_season,
        "model_version": "0.1.1-backtest",
        "generated_at": datetime.now(UTC).isoformat(),
        "method": {
            "training_seasons": sorted(int(value) for value in train.season.unique()),
            "feature_cutoff": "start of each NFL week",
            "qb_starter_proxy": "most dropbacks in team's latest completed game",
            "injuries": "not used",
            "market_lines": "not used",
        },
        "metrics": {
            "games": len(test),
            "brier": _brier(y, probability),
            "log_loss": _log_loss(y, probability),
            "accuracy": float(((probability >= 0.5) == y).mean()),
            "baseline_home_rate": historical_home_rate,
            "baseline_brier": _brier(y, baseline),
            "baseline_log_loss": _log_loss(y, baseline),
        },
        "calibration": _calibration(test),
        "weekly": weekly,
        "games": test[
            [
                "game_id", "week", "gameday", "away_team", "home_team", "away_score",
                "home_score", "probability", "home_win",
            ]
        ].to_dict("records"),
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
