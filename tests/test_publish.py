import json
from pathlib import Path

import pytest

from vaimea.publish import build_history


def _write(path: Path, payload: dict):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_publish_keeps_latest_snapshot_per_game(tmp_path):
    ledger = tmp_path / "ledger"
    public = tmp_path / "public"
    ledger.mkdir()
    _write(
        ledger / "1.json",
        {
            "status": "official",
            "cutoff": "2026-09-09T18:00:00+00:00",
            "approved_at": "2026-09-09T18:01:00+00:00",
            "model_version": "0.1.1",
            "source_week": 1,
            "forecasts": [
                {"game_id": "g1", "kickoff": "2026-09-10T00:20:00+00:00", "final_lock_at": "2026-09-09T22:50:00+00:00", "home_win_probability": 0.60},
                {"game_id": "g2", "kickoff": "2026-09-13T17:00:00+00:00", "final_lock_at": "2026-09-13T15:30:00+00:00", "home_win_probability": 0.55},
            ],
        },
    )
    _write(
        ledger / "2.json",
        {
            "status": "official",
            "cutoff": "2026-09-12T18:00:00+00:00",
            "approved_at": "2026-09-12T18:01:00+00:00",
            "model_version": "0.1.1",
            "source_week": 1,
            "forecasts": [
                {"game_id": "g2", "kickoff": "2026-09-13T17:00:00+00:00", "final_lock_at": "2026-09-13T15:30:00+00:00", "home_win_probability": 0.58},
            ],
        },
    )
    build_history(ledger, public)
    latest = json.loads((public / "latest.json").read_text())
    probs = {row["game_id"]: row["home_win_probability"] for row in latest["forecasts"]}
    assert probs == {"g1": 0.60, "g2": 0.58}
    movers = json.loads((public / "movers.json").read_text())
    assert len(movers) == 1
    assert movers[0]["game_id"] == "g2"
    assert movers[0]["move"] == pytest.approx(0.03)


def test_status_uses_latest_operational_data_time(tmp_path):
    ledger = tmp_path / "ledger"
    public = tmp_path / "public"
    ledger.mkdir()
    public.mkdir()
    _write(
        ledger / "1.json",
        {
            "status": "official",
            "cutoff": "2026-09-09T18:00:00+00:00",
            "data_fetched_at": "2026-09-09T17:00:00+00:00",
            "forecasts": [],
        },
    )
    _write(public / "data-quality.json", {"checked_at": "2026-09-10T10:17:00+00:00"})
    build_history(ledger, public)
    status = json.loads((public / "status.json").read_text())
    assert status["data_fetched_at"] == "2026-09-10T10:17:00+00:00"
    assert status["official_forecast_data_fetched_at"] == "2026-09-09T17:00:00+00:00"
