import json

import pytest

from vaimea.season_history import (
    archive_snapshot,
    audit_history,
    build_public_history,
    run_simulation_snapshot,
)


def _snapshot(as_of="2026-09-01T12:00:00+00:00", playoff=0.7):
    return {
        "season": 2026,
        "week": "PRE",
        "as_of": as_of,
        "model_version": "0.1.1",
        "simulation_count": 100000,
        "tiebreaker_mode": "approximation_v0.1",
        "teams": [
            {
                "team": "BUF",
                "playoff_probability": playoff,
                "division_probability": 0.5,
                "conference_probability": None,
                "super_bowl_probability": None,
            },
            {
                "team": "KC",
                "playoff_probability": 0.75,
                "division_probability": 0.55,
                "conference_probability": None,
                "super_bowl_probability": None,
            },
        ],
    }


def test_season_history_is_append_only_and_deduplicates_identical_runs(tmp_path):
    source = tmp_path / "latest.json"
    ledger = tmp_path / "ledger"
    output = tmp_path / "public" / "season-history.json"
    source.write_text(json.dumps(_snapshot()), encoding="utf-8")
    first = archive_snapshot(source, ledger)
    duplicate = archive_snapshot(source, ledger)
    assert first == duplicate
    assert len(list(ledger.glob("*.json"))) == 1

    changed = _snapshot("2026-09-08T12:00:00+00:00", playoff=0.74)
    changed["week"] = 1
    source.write_text(json.dumps(changed), encoding="utf-8")
    archive_snapshot(source, ledger)
    public = build_public_history(ledger, output)
    assert len(public["snapshots"]) == 2
    assert public["latest"]["week"] == 1
    assert public["availability"]["playoff_probability"] is True
    assert public["availability"]["super_bowl_probability"] is False
    assert audit_history(ledger)["status"] == "ok"


def test_season_history_rejects_invalid_probability(tmp_path):
    source = tmp_path / "latest.json"
    payload = _snapshot()
    payload["teams"][0]["playoff_probability"] = 1.1
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="between zero and one"):
        archive_snapshot(source, tmp_path / "ledger")


def test_season_history_audit_detects_changed_snapshot(tmp_path):
    source = tmp_path / "latest.json"
    ledger = tmp_path / "ledger"
    source.write_text(json.dumps(_snapshot()), encoding="utf-8")
    archived = archive_snapshot(source, ledger)
    payload = json.loads(archived.read_text(encoding="utf-8"))
    payload["teams"][0]["playoff_probability"] = 0.1
    archived.write_text(json.dumps(payload), encoding="utf-8")
    assert audit_history(ledger)["status"] == "failed"


def test_run_simulation_snapshot_writes_chart_contract(tmp_path):
    teams = [f"T{i:02d}" for i in range(16)]
    payload = {
        "season": 2026,
        "week": "PRE",
        "as_of": "2026-09-01T12:00:00+00:00",
        "model_version": "0.1.1",
        "simulation_count": 100,
        "random_seed": 7,
        "team_meta": [
            {
                "team": team,
                "conference": "A" if index < 8 else "N",
                "division": f"{'A' if index < 8 else 'N'}{(index % 8) // 4}",
            }
            for index, team in enumerate(teams)
        ],
        "schedule": [
            {
                "home_team": team,
                "away_team": teams[(index + game + 1) % len(teams)],
                "home_win_probability": 0.5,
            }
            for index, team in enumerate(teams)
            for game in range(2)
        ],
    }
    source = tmp_path / "input.json"
    output = tmp_path / "latest.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    snapshot = run_simulation_snapshot(source, output)
    assert output.exists()
    assert snapshot["simulation_count"] == 100
    assert len(snapshot["teams"]) == 16
    assert all("division_probability" in row for row in snapshot["teams"])
