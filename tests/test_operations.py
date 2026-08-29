import json
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from vaimea.monitoring import performance_report
from vaimea.operations import (
    approve_forecast,
    create_draft,
    make_review,
    recovery_audit,
    suggest_starters,
)


def _draft():
    now = datetime.now(UTC)
    return {
        "model_version": "0.1.1",
        "cutoff": now.isoformat(),
        "data_fetched_at": (now - timedelta(hours=2)).isoformat(),
        "source_week": 1,
        "random_seed": 7,
        "input_hashes": {"pbp": "abc"},
        "data_quality": {"pbp_rows": 50000, "games": 200, "teams": 32, "qb_coverage": 1.0},
        "tiebreaker_mode": "approximation_v0.1",
        "forecasts": [
            {
                "game_id": "g1",
                "kickoff": (now + timedelta(days=2)).isoformat(),
                "home_team": "A",
                "away_team": "B",
                "home_qb_id": "qa",
                "away_qb_id": "qb",
                "home_win_probability": 0.6,
                "neutral_site": False,
            }
        ],
    }


def _approvals(approved=True):
    return {"games": {"g1": {"home_qb_id": "qa", "away_qb_id": "qb", "approved": approved}}}


def test_starter_suggestions_are_asof_and_need_review():
    schedule = pd.DataFrame([{"game_id": "g1", "home_team": "A", "away_team": "B"}])
    chart = pd.DataFrame(
        [
            {"team": "A", "player_id": "old", "position": "QB", "depth_order": 1, "available_at": "2026-08-01"},
            {"team": "A", "player_id": "future", "position": "QB", "depth_order": 1, "available_at": "2026-09-01"},
            {"team": "B", "player_id": "b", "position": "QB", "depth_order": 1, "available_at": "2026-08-01"},
        ]
    )
    result = suggest_starters(schedule, chart, "2026-08-20T00:00:00Z")
    assert result["g1"]["home_qb_id"] == "old"
    assert result["g1"]["approved"] is False


def test_review_blocks_unapproved_qb_and_accepts_reviewed_qb():
    assert make_review(_draft(), _approvals(False))["status"] == "blocked"
    ready = make_review(_draft(), _approvals(True))
    assert ready["status"] == "ready"
    assert "tiebreaker_approximation" in ready["games"][0]["warnings"]


def test_approval_is_append_only_and_reproducible(tmp_path):
    draft = tmp_path / "draft.json"
    approvals = tmp_path / "approvals.json"
    config = tmp_path / "model.yaml"
    draft.write_text(json.dumps(_draft()), encoding="utf-8")
    approvals.write_text(json.dumps(_approvals()), encoding="utf-8")
    config.write_text("model_version: 0.1.1\n", encoding="utf-8")
    ledger = tmp_path / "ledger"
    path = approve_forecast(draft, approvals, ledger, "tester", config)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "official"
    assert payload["reproducibility"]["draft_sha256"]
    with pytest.raises(FileExistsError):
        approve_forecast(draft, approvals, ledger, "tester", config)
    assert recovery_audit(ledger)["status"] == "ok"


def test_performance_monitor_includes_baselines_without_refitting():
    rows = pd.DataFrame(
        {
            "home_win": [1, 0, 1, 1],
            "home_win_probability": [0.7, 0.4, 0.6, 0.55],
            "elo_home_probability": [0.6, 0.45, 0.55, 0.52],
        }
    )
    report = performance_report(rows, rolling_games=3)
    assert report["model"]["games"] == 4
    assert "constant_home_rate" in report["baselines"]
    assert "elo" in report["baselines"]
    assert "not refitted" in report["calibration_note"]


def test_draft_packages_probabilities_without_changing_them(tmp_path):
    forecasts = tmp_path / "forecasts.csv"
    quality = tmp_path / "quality.json"
    output = tmp_path / "draft.json"
    pd.DataFrame(_draft()["forecasts"]).to_csv(forecasts, index=False)
    quality.write_text(
        json.dumps({"summary": {"pbp_rows": 50000, "games": 200, "teams": 32}}),
        encoding="utf-8",
    )
    result = create_draft(
        forecasts,
        quality,
        output,
        _draft()["cutoff"],
        _draft()["data_fetched_at"],
        1,
        "0.1.1",
        7,
    )
    assert result["forecasts"][0]["home_win_probability"] == 0.6
    assert result["status"] == "needs_review"
