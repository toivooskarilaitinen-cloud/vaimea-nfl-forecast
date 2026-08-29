from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pandas as pd


def _scores(y: np.ndarray, p: np.ndarray) -> dict:
    p = np.clip(p.astype(float), 1e-15, 1 - 1e-15)
    y = y.astype(float)
    return {
        "games": int(len(y)),
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
