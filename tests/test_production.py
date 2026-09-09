
import pandas as pd
import pytest

from vaimea.operations import confirm_starters, make_review
from vaimea.production import prepare_review_package
from vaimea.quality import QualityError


def _season_input():
    return {
        "season": 2026,
        "model_version": "0.1.1",
        "random_seed": 20260826,
        "tiebreaker_mode": "approximation_v0.1",
        "schedule": [
            {
                "game_id": "2026_01_NE_SEA",
                "week": 1,
                "gameday": "2026-09-09",
                "away_team": "NE",
                "home_team": "SEA",
                "home_win_probability": 0.5986043070911548,
            },
            {
                "game_id": "2026_01_SF_LA",
                "week": 1,
                "gameday": "2026-09-10",
                "away_team": "SF",
                "home_team": "LA",
                "home_win_probability": 0.5590723043913901,
            },
        ],
    }


def _games():
    return pd.DataFrame(
        [
            {
                "game_id": "2026_01_NE_SEA",
                "season": 2026,
                "game_type": "REG",
                "gameday": "2026-09-09",
                "gametime": "20:20",
                "away_team": "NE",
                "home_team": "SEA",
                "location": "Home",
                "away_qb_id": "maye",
                "home_qb_id": "darnold",
                "away_qb_name": "Drake Maye",
                "home_qb_name": "Sam Darnold",
            },
            {
                "game_id": "2026_01_SF_LA",
                "season": 2026,
                "game_type": "REG",
                "gameday": "2026-09-10",
                "gametime": "20:35",
                "away_team": "SF",
                "home_team": "LA",
                "location": "Neutral",
                "away_qb_id": "purdy",
                "home_qb_id": "stafford",
                "away_qb_name": "Brock Purdy",
                "home_qb_name": "Matthew Stafford",
            },
        ]
    )


def _preseason():
    return {
        "teams": [
            {"team": "NE", "player_id": "maye", "player_name": "Drake Maye"},
            {"team": "SEA", "player_id": "darnold", "player_name": "Sam Darnold"},
            {"team": "SF", "player_id": "purdy", "player_name": "Brock Purdy"},
            {"team": "LA", "player_id": "stafford", "player_name": "Matthew Stafford"},
        ]
    }


def _quality():
    return {
        "checked_at": "2026-09-09T20:00:00+00:00",
        "summary": {"pbp_rows": 98000, "games": 570, "teams": 32, "qb_coverage": 0.94},
    }


def test_prepare_review_package_builds_week_and_final_lock(tmp_path):
    draft, starters, request = prepare_review_package(
        _season_input(),
        _games(),
        _quality(),
        _preseason(),
        tmp_path,
        now=pd.Timestamp("2026-09-09T20:30:00Z"),
        final_lock_minutes=90,
    )
    assert request["review_needed"] is True
    assert draft["source_week"] == 1
    assert len(draft["forecasts"]) == 2
    opener = next(x for x in draft["forecasts"] if x["game_id"] == "2026_01_NE_SEA")
    assert opener["home_win_probability"] == pytest.approx(0.5986043070911548)
    assert opener["home_qb_id"] == "darnold"
    assert opener["probability_home_qb_id"] == "darnold"
    assert opener["final_lock_at"] == "2026-09-09T22:50:00+00:00"
    assert starters["games"]["2026_01_NE_SEA"]["approved"] is False


def test_prepare_review_package_skips_game_after_final_lock(tmp_path):
    draft, _, _ = prepare_review_package(
        _season_input(),
        _games(),
        _quality(),
        _preseason(),
        tmp_path,
        now=pd.Timestamp("2026-09-10T03:00:00Z"),
        final_lock_minutes=90,
    )
    assert [x["game_id"] for x in draft["forecasts"]] == ["2026_01_SF_LA"]


def test_qb_change_is_detected_and_blocks_review(tmp_path):
    games = _games()
    games.loc[games.game_id == "2026_01_NE_SEA", "home_qb_id"] = "backup"
    draft, starters, _ = prepare_review_package(
        _season_input(),
        games,
        _quality(),
        _preseason(),
        tmp_path,
        now=pd.Timestamp("2026-09-09T20:30:00Z"),
    )
    starters = confirm_starters(starters, "owner", "APPROVE")
    review = make_review(draft, starters, now=pd.Timestamp("2026-09-09T21:00:00Z"))
    assert review["status"] == "blocked"
    assert any("home QB changed; probability must be recomputed" in x for x in review["errors"])


def test_final_lock_blocks_late_approval(tmp_path):
    draft, starters, _ = prepare_review_package(
        _season_input(),
        _games(),
        _quality(),
        _preseason(),
        tmp_path,
        now=pd.Timestamp("2026-09-09T20:30:00Z"),
    )
    starters = confirm_starters(starters, "owner", "APPROVE")
    review = make_review(draft, starters, now=pd.Timestamp("2026-09-09T22:50:00Z"))
    assert review["status"] == "blocked"
    assert any("final lock has passed" in x for x in review["errors"])


def test_starter_sheet_must_match_exact_draft_cutoff(tmp_path):
    draft, starters, _ = prepare_review_package(
        _season_input(),
        _games(),
        _quality(),
        _preseason(),
        tmp_path,
        now=pd.Timestamp("2026-09-09T20:30:00Z"),
    )
    starters = confirm_starters(starters, "owner", "APPROVE")
    starters["cutoff"] = "2026-09-09T20:31:00+00:00"
    review = make_review(draft, starters, now=pd.Timestamp("2026-09-09T21:00:00Z"))
    assert review["status"] == "blocked"
    assert "starter review cutoff does not match draft cutoff" in review["errors"]


def test_confirmation_requires_explicit_approve():
    with pytest.raises(QualityError):
        confirm_starters({"games": {"g": {}}}, "owner", "yes")
