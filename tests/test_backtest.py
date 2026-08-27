import pandas as pd

from vaimea.backtest import _calibration, _starter_proxy


def test_starter_proxy_uses_latest_completed_game():
    rows = pd.DataFrame(
        [
            {"posteam": "A", "game_date": "2025-09-01", "qb_dropback": 1, "passer_player_id": "old"},
            {"posteam": "A", "game_date": "2025-09-08", "qb_dropback": 1, "passer_player_id": "new"},
            {"posteam": "A", "game_date": "2025-09-08", "qb_dropback": 1, "passer_player_id": "new"},
        ]
    )
    rows["game_date"] = pd.to_datetime(rows.game_date)
    assert _starter_proxy(rows)["A"] == "new"


def test_calibration_counts_every_game():
    rows = pd.DataFrame({"probability": [0.2, 0.55, 0.8], "home_win": [0, 1, 1]})
    assert sum(item["n"] for item in _calibration(rows)) == 3
