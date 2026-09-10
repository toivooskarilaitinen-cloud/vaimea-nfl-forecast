import pandas as pd

from vaimea.quality import missing_mature_results


def test_only_mature_completed_games_must_exist_in_pbp():
    games = pd.DataFrame(
        [
            {
                "game_id": "old",
                "season": 2026,
                "gameday": "2026-09-01",
                "home_score": 20,
                "away_score": 10,
            },
            {
                "game_id": "recent",
                "season": 2026,
                "gameday": "2026-09-09",
                "home_score": 20,
                "away_score": 10,
            },
        ]
    )
    pbp = pd.DataFrame([{"game_id": "other", "season": 2026}])
    missing = missing_mature_results(
        games, pbp, 2026, pd.Timestamp("2026-09-10T12:00:00Z"), grace_hours=96
    )
    assert missing == ["old"]
