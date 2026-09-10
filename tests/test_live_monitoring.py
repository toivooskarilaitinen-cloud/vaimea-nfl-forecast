import json
from pathlib import Path

import pandas as pd
import pytest

from vaimea.monitoring import publish_live_performance, score_official_forecasts


def _write_snapshot(path: Path, approved_at: str, probability: float):
    path.write_text(
        json.dumps(
            {
                "status": "official",
                "approved_at": approved_at,
                "approved_by": "tester",
                "cutoff": approved_at,
                "model_version": "0.1.1",
                "forecasts": [
                    {
                        "game_id": "g1",
                        "week": 1,
                        "gameday": "2026-09-09",
                        "kickoff": "2026-09-10T00:20:00+00:00",
                        "final_lock_at": "2026-09-09T22:50:00+00:00",
                        "away_team": "NE",
                        "home_team": "SEA",
                        "home_win_probability": probability,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_scores_latest_official_forecast_before_final_lock(tmp_path):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    _write_snapshot(ledger / "1.json", "2026-09-09T15:00:00+00:00", 0.58)
    _write_snapshot(ledger / "2.json", "2026-09-09T16:00:00+00:00", 0.60)
    _write_snapshot(ledger / "too-late.json", "2026-09-09T23:00:00+00:00", 0.99)
    games = pd.DataFrame(
        [{"game_id": "g1", "away_score": 10, "home_score": 13, "result": 3}]
    )

    rows = score_official_forecasts(ledger, games)

    assert len(rows) == 1
    assert rows[0]["home_win_probability"] == 0.60
    assert rows[0]["winner"] == "SEA"
    assert rows[0]["favorite_correct"] is True
    assert rows[0]["brier"] == pytest.approx(0.16)


def test_publishes_metrics_and_public_history(tmp_path):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    _write_snapshot(ledger / "1.json", "2026-09-09T16:00:00+00:00", 0.60)
    games = pd.DataFrame(
        [{"game_id": "g1", "away_score": 10, "home_score": 13, "result": 3}]
    )
    output = tmp_path / "public" / "performance.json"

    report = publish_live_performance(ledger, output, games=games)

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert report["model"]["games"] == 1
    assert report["model"]["brier"] == pytest.approx(0.16)
    assert saved["forecasts"][0]["game_id"] == "g1"


def test_publishes_empty_report_before_first_result(tmp_path):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    _write_snapshot(ledger / "1.json", "2026-09-09T16:00:00+00:00", 0.60)
    games = pd.DataFrame(
        [{"game_id": "g1", "away_score": None, "home_score": None, "result": None}]
    )
    output = tmp_path / "performance.json"

    report = publish_live_performance(ledger, output, games=games)

    assert report["model"] == {"games": 0, "brier": None, "log_loss": None}
    assert report["forecasts"] == []
