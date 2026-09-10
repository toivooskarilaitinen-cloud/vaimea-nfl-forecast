from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .io import atomic_json
from .production import load_games


def _scores(y: np.ndarray, p: np.ndarray) -> dict:
    p = np.clip(p.astype(float), 1e-15, 1 - 1e-15)
    y = y.astype(float)
    return {
        "games": len(y),
        "brier": float(np.mean((p - y) ** 2)),
        "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
    }


def performance_report(rows: pd.DataFrame, rolling_games: int = 100) -> dict:
    required = {"home_win", "home_win_probability"}
    missing = required - set(rows.columns)
    if missing or rows.empty:
        raise ValueError(f"performance rows missing: {sorted(missing)}")
    frame = rows.copy()
    y = frame.home_win.to_numpy(float)
    probability = frame.home_win_probability.to_numpy(float)
    home_rate = np.repeat(y.mean(), len(y))
    bins = pd.cut(probability, np.linspace(0, 1, 11), include_lowest=True)
    calibration = (
        frame.assign(bin=bins)
        .groupby("bin", observed=True)
        .agg(n=("home_win", "size"), predicted=("home_win_probability", "mean"), observed=("home_win", "mean"))
        .reset_index()
    )
    calibration["bin"] = calibration.bin.astype(str)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model": _scores(y, probability),
        "rolling": _scores(y[-rolling_games:], probability[-rolling_games:]),
        "baselines": {"constant_home_rate": _scores(y, home_rate)},
        "calibration": calibration.to_dict("records"),
        "calibration_note": "Monitoring only. The frozen in-season model is not refitted from this report.",
    }
    if "elo_home_probability" in frame:
        report["baselines"]["elo"] = _scores(y, frame.elo_home_probability.to_numpy(float))
    if "market_home_probability" in frame:
        available = frame.market_home_probability.notna()
        if available.any():
            report["baselines"]["timestamped_market"] = _scores(
                frame.loc[available, "home_win"].to_numpy(float),
                frame.loc[available, "market_home_probability"].to_numpy(float),
            )
    report["standard_error_at_50pct"] = 0.5 / math.sqrt(len(y))
    return report


def _timestamp(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _latest_locked_forecasts(ledger_dir: Path) -> dict[str, dict]:
    """Return one immutable, final pre-game forecast for each game."""
    latest: dict[str, dict] = {}
    for path in sorted(ledger_dir.glob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        if entry.get("status") != "official":
            continue
        approved_at = _timestamp(entry.get("approved_at") or entry.get("cutoff"))
        for forecast in entry.get("forecasts", []):
            game_id = forecast.get("game_id")
            lock_at = _timestamp(forecast.get("final_lock_at") or forecast.get("kickoff"))
            if not game_id or approved_at is None or lock_at is None or approved_at > lock_at:
                continue
            candidate = {
                **forecast,
                "forecast_cutoff": entry.get("cutoff"),
                "approved_at": entry.get("approved_at"),
                "approved_by": entry.get("approved_by"),
                "model_version": entry.get("model_version"),
                "_approved_at": approved_at,
            }
            previous = latest.get(game_id)
            if previous is None or approved_at > previous["_approved_at"]:
                latest[game_id] = candidate
    return latest


def score_official_forecasts(ledger_dir: Path, games: pd.DataFrame) -> list[dict]:
    """Join final official probabilities to completed, non-tied game results."""
    required = {"game_id", "away_score", "home_score"}
    missing = required - set(games.columns)
    if missing:
        raise ValueError(f"result data missing: {sorted(missing)}")

    results = games.drop_duplicates("game_id", keep="last").set_index("game_id", drop=False)
    scored = []
    for game_id, forecast in _latest_locked_forecasts(ledger_dir).items():
        if game_id not in results.index:
            continue
        result = results.loc[game_id]
        home_score, away_score = result.get("home_score"), result.get("away_score")
        if pd.isna(home_score) or pd.isna(away_score) or float(home_score) == float(away_score):
            continue
        if "result" in results.columns and pd.isna(result.get("result")):
            continue

        probability = float(forecast["home_win_probability"])
        if not 0 <= probability <= 1:
            raise ValueError(f"{game_id}: probability outside [0,1]")
        home_win = int(float(home_score) > float(away_score))
        clipped = float(np.clip(probability, 1e-15, 1 - 1e-15))
        winner = forecast["home_team"] if home_win else forecast["away_team"]
        predicted_winner = (
            forecast["home_team"] if probability >= 0.5 else forecast["away_team"]
        )
        scored.append(
            {
                "game_id": game_id,
                "week": forecast.get("week"),
                "gameday": forecast.get("gameday"),
                "kickoff": forecast.get("kickoff"),
                "away_team": forecast.get("away_team"),
                "home_team": forecast.get("home_team"),
                "away_score": int(float(away_score)),
                "home_score": int(float(home_score)),
                "home_win": home_win,
                "home_win_probability": probability,
                "predicted_winner": predicted_winner,
                "winner": winner,
                "favorite_correct": predicted_winner == winner,
                "brier": float((probability - home_win) ** 2),
                "log_loss": float(
                    -(home_win * math.log(clipped) + (1 - home_win) * math.log(1 - clipped))
                ),
                "forecast_cutoff": forecast.get("forecast_cutoff"),
                "approved_at": forecast.get("approved_at"),
                "approved_by": forecast.get("approved_by"),
                "final_lock_at": forecast.get("final_lock_at"),
                "model_version": forecast.get("model_version"),
            }
        )
    return sorted(scored, key=lambda row: (row.get("kickoff") or "", row["game_id"]))


def publish_live_performance(
    ledger_dir: Path = Path("data/forecast-ledger"),
    output: Path = Path("public/data/performance.json"),
    games: pd.DataFrame | None = None,
    rolling_games: int = 100,
) -> dict:
    """Build the public live track record directly from immutable forecasts and results."""
    rows = score_official_forecasts(ledger_dir, games if games is not None else load_games())
    if rows:
        report = performance_report(pd.DataFrame(rows), rolling_games)
    else:
        empty = {"games": 0, "brier": None, "log_loss": None}
        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "model": empty,
            "rolling": empty,
            "baselines": {},
            "calibration": [],
            "calibration_note": (
                "Monitoring only. The frozen in-season model is not refitted from this report."
            ),
            "standard_error_at_50pct": None,
        }
    report["forecasts"] = rows
    report["selection_rule"] = "latest official forecast approved no later than T-90"
    atomic_json(output, report)
    return report
