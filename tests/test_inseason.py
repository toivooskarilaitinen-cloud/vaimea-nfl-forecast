import json

import numpy as np
import pandas as pd

from vaimea import inseason


class _StrengthModel:
    def predict_proba(self, frame):
        probability = 1 / (1 + np.exp(-frame.strength_diff.to_numpy()))
        return np.c_[1 - probability, probability]


def _pbp(current_epa=None):
    rows = []
    for index in range(8):
        rows.extend([
            {"game_id": f"2025_{index}", "season": 2025, "game_date": "2025-12-01",
             "posteam": "A", "defteam": "B", "epa": 0.1, "cpoe": 0.0,
             "qb_dropback": 1, "passer_player_id": "qa", "passer_player_name": "QA"},
            {"game_id": f"2025_{index}", "season": 2025, "game_date": "2025-12-01",
             "posteam": "B", "defteam": "A", "epa": -0.1, "cpoe": 0.0,
             "qb_dropback": 1, "passer_player_id": "qb", "passer_player_name": "QB"},
        ])
    if current_epa is not None:
        rows.extend([
            {"game_id": "2026_played", "season": 2026, "game_date": "2026-09-01",
             "posteam": "A", "defteam": "B", "epa": current_epa, "cpoe": 0.0,
             "qb_dropback": 1, "passer_player_id": "qa", "passer_player_name": "QA"},
            {"game_id": "2026_played", "season": 2026, "game_date": "2026-09-01",
             "posteam": "B", "defteam": "A", "epa": -current_epa, "cpoe": 0.0,
             "qb_dropback": 1, "passer_player_id": "qb", "passer_player_name": "QB"},
        ])
    return pd.DataFrame(rows)


def test_current_season_play_changes_future_probability_and_completed_game_is_fixed(
    tmp_path, monkeypatch
):
    input_path = tmp_path / "input.json"
    review_path = tmp_path / "review.json"
    ratings_path = tmp_path / "ratings.json"
    input_path.write_text(json.dumps({"season": 2026, "model_version": "test",
        "team_meta": [], "schedule": [], "playoff_matchups": [], "provenance": {}}))
    review_path.write_text(json.dumps({"teams": [
        {"team": "A", "player_id": "qa"}, {"team": "B", "player_id": "qb"}]}))
    games = pd.DataFrame([
        {"game_id": "2026_played", "season": 2026, "game_type": "REG", "week": 1,
         "gameday": "2026-09-01", "gametime": "20:00", "home_team": "A",
         "away_team": "B", "home_score": 24, "away_score": 17,
         "home_qb_id": "qa", "away_qb_id": "qb"},
        {"game_id": "2026_future", "season": 2026, "game_type": "REG", "week": 2,
         "gameday": "2026-09-20", "gametime": "20:00", "home_team": "A",
         "away_team": "B", "home_score": np.nan, "away_score": np.nan,
         "home_qb_id": "qa", "away_qb_id": "qb"},
    ])
    monkeypatch.setattr(inseason, "build_game_features", lambda *args, **kwargs:
                        pd.DataFrame({"home_win": [0, 1] * 51}))
    monkeypatch.setattr(inseason, "fit", lambda _: _StrengthModel())
    monkeypatch.setattr(inseason, "apply_temperature", lambda values, slope: values)
    monkeypatch.setattr(inseason, "load_clean_pbp", lambda *args: _pbp())
    before = inseason.update_season_input(tmp_path, input_path, review_path, ratings_path,
        now=pd.Timestamp("2026-09-10T00:00:00Z"), games=games)
    monkeypatch.setattr(inseason, "load_clean_pbp", lambda *args: _pbp(2.0))
    after = inseason.update_season_input(tmp_path, input_path, review_path, ratings_path,
        now=pd.Timestamp("2026-09-10T00:00:00Z"), games=games)
    before_future = next(row for row in before["schedule"] if row["game_id"] == "2026_future")
    after_future = next(row for row in after["schedule"] if row["game_id"] == "2026_future")
    played = next(row for row in after["schedule"] if row["game_id"] == "2026_played")
    assert after_future["home_win_probability"] > before_future["home_win_probability"]
    assert played["home_win_probability"] == 1.0
    assert played["completed"] is True
    assert after["provenance"]["current_season_updates"] is True
