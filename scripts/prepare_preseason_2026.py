from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from vaimea.backtest import build_game_features
from vaimea.features import game_context, qb_strength, team_strength
from vaimea.model import FEATURES, apply_temperature, fit
from vaimea.season_history import run_simulation_snapshot


CACHE = Path("data/preseason-cache")
TEMPERATURE_SLOPE = 0.869
QB = {
    "ARI": ("Jacoby Brissett", "00-0033119"), "ATL": ("Tua Tagovailoa", "00-0036212"),
    "BAL": ("Lamar Jackson", "00-0034796"), "BUF": ("Josh Allen", "00-0034857"),
    "CAR": ("Bryce Young", "00-0039150"), "CHI": ("Caleb Williams", "00-0039918"),
    "CIN": ("Joe Burrow", "00-0036442"), "CLE": ("Deshaun Watson", "00-0033537"),
    "DAL": ("Dak Prescott", "00-0033077"), "DEN": ("Bo Nix", "00-0039732"),
    "DET": ("Jared Goff", "00-0033106"), "GB": ("Jordan Love", "00-0036264"),
    "HOU": ("C.J. Stroud", "00-0039163"), "IND": ("Daniel Jones", "00-0035710"),
    "JAX": ("Trevor Lawrence", "00-0036971"), "KC": ("Patrick Mahomes", "00-0033873"),
    "LA": ("Matthew Stafford", "00-0026498"), "LAC": ("Justin Herbert", "00-0036355"),
    "LV": ("Kirk Cousins", "00-0029604"), "MIA": ("Malik Willis", "00-0038128"),
    "MIN": ("Kyler Murray", "00-0035228"), "NE": ("Drake Maye", "00-0039851"),
    "NO": ("Tyler Shough", "00-0040743"), "NYG": ("Jaxson Dart", "00-0040691"),
    "NYJ": ("Geno Smith", "00-0030565"), "PHI": ("Jalen Hurts", "00-0036389"),
    "PIT": ("Aaron Rodgers", "00-0023459"), "SEA": ("Sam Darnold", "00-0034869"),
    "SF": ("Brock Purdy", "00-0037834"), "TB": ("Baker Mayfield", "00-0034855"),
    "TEN": ("Cam Ward", "00-0040676"), "WAS": ("Jayden Daniels", "00-0039910"),
}

DIVISIONS = {
    "AFC East": ["BUF", "MIA", "NE", "NYJ"], "AFC North": ["BAL", "CIN", "CLE", "PIT"],
    "AFC South": ["HOU", "IND", "JAX", "TEN"], "AFC West": ["DEN", "KC", "LAC", "LV"],
    "NFC East": ["DAL", "NYG", "PHI", "WAS"], "NFC North": ["CHI", "DET", "GB", "MIN"],
    "NFC South": ["ATL", "CAR", "NO", "TB"], "NFC West": ["ARI", "LA", "SEA", "SF"],
}


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    schedule = pd.read_csv(CACHE / "schedules.csv", low_memory=False)
    schedule["gameday"] = pd.to_datetime(schedule.gameday)
    wanted = [
        "game_id", "season", "week", "game_date", "home_team", "away_team", "posteam",
        "defteam", "epa", "cpoe", "qb_dropback", "passer_player_id", "passer_player_name",
    ]
    frames = []
    for season in range(2018, 2026):
        frame = pd.read_csv(CACHE / f"pbp_{season}.csv.gz", usecols=lambda column: column in wanted)
        frames.append(frame)
    pbp = pd.concat(frames, ignore_index=True)
    pbp["game_date"] = pd.to_datetime(pbp.game_date)
    return schedule, pbp.sort_values(["game_date", "game_id"]).reset_index(drop=True)


def main() -> None:
    schedule, pbp = load_data()
    features = build_game_features(schedule, pbp, list(range(2021, 2026)))
    model = fit(features)

    recent_ids = pbp[["game_id", "game_date"]].drop_duplicates().tail(640).game_id
    history = pbp[pbp.game_id.isin(recent_ids)]
    teams = team_strength(history).set_index("team")
    qbs = qb_strength(history).set_index("passer_player_id")

    games = schedule[(schedule.season == 2026) & schedule.game_type.eq("REG")].copy()
    games = games.sort_values(["week", "gameday", "gametime", "game_id"])
    context = game_context(games).set_index("game_id")
    rows = []
    for game in games.itertuples():
        home_strength = float(teams.loc[game.home_team, ["offense_epa_adj", "defense_epa_adj"]].sum())
        away_strength = float(teams.loc[game.away_team, ["offense_epa_adj", "defense_epa_adj"]].sum())
        home_qb_id = QB[game.home_team][1]
        away_qb_id = QB[game.away_team][1]
        home_qb = float(qbs.loc[home_qb_id, "qb_rating"]) if home_qb_id in qbs.index else 0.0
        away_qb = float(qbs.loc[away_qb_id, "qb_rating"]) if away_qb_id in qbs.index else 0.0
        ctx = context.loc[game.game_id]
        rows.append({
            "game_id": game.game_id, "week": int(game.week), "gameday": str(game.gameday.date()),
            "away_team": game.away_team, "home_team": game.home_team,
            "strength_diff": home_strength - away_strength, "qb_diff": home_qb - away_qb,
            "home_field": float(ctx.home_field), "rest_diff": float(ctx.rest_diff),
            "home_qb": QB[game.home_team][0], "away_qb": QB[game.away_team][0],
        })
    forecast = pd.DataFrame(rows)
    raw = model.predict_proba(forecast[FEATURES])[:, 1]
    forecast["home_win_probability"] = apply_temperature(raw, TEMPERATURE_SLOPE)

    playoff_rows = []
    for home_team in sorted(QB):
        for away_team in sorted(QB):
            if home_team == away_team:
                continue
            home_strength = float(
                teams.loc[home_team, ["offense_epa_adj", "defense_epa_adj"]].sum()
            )
            away_strength = float(
                teams.loc[away_team, ["offense_epa_adj", "defense_epa_adj"]].sum()
            )
            home_id, away_id = QB[home_team][1], QB[away_team][1]
            home_qb = float(qbs.loc[home_id, "qb_rating"])
            away_qb = float(qbs.loc[away_id, "qb_rating"])
            base = {
                "strength_diff": home_strength - away_strength,
                "qb_diff": home_qb - away_qb,
            }
            contexts = pd.DataFrame([
                {**base, "home_field": 1.0, "rest_diff": 0.0},
                {**base, "home_field": 1.0, "rest_diff": 7.0},
                {**base, "home_field": 0.0, "rest_diff": 0.0},
            ])
            probability = apply_temperature(
                model.predict_proba(contexts[FEATURES])[:, 1], TEMPERATURE_SLOPE
            )
            playoff_rows.append({
                "home_team": home_team,
                "away_team": away_team,
                "home_win_probability": float(probability[0]),
                "bye_home_win_probability": float(probability[1]),
                "neutral_win_probability": float(probability[2]),
            })

    team_meta = []
    for division, members in DIVISIONS.items():
        conference = division.split()[0]
        team_meta.extend({"team": team, "conference": conference, "division": division} for team in members)

    cutoff = datetime.now(UTC).replace(microsecond=0).isoformat()
    review = {
        "kind": "preseason_qb_review", "season": 2026, "cutoff": cutoff,
        "source": "nflverse depth_charts_2026.csv", "source_as_of": "2026-08-30T12:30:54Z",
        "approved_by": "repository_owner", "approved_in_conversation": True,
        "teams": [{"team": team, "player_name": name, "player_id": player_id, "approved": True}
                  for team, (name, player_id) in sorted(QB.items())],
    }
    input_payload = {
        "season": 2026, "week": "PRE", "as_of": cutoff, "model_version": "0.1.1",
        "simulation_count": 100000, "random_seed": 20260826,
        "tiebreaker_mode": "approximation_v0.1", "team_meta": team_meta,
        "playoff_format": "NFL_14_team_reseed_v1",
        "playoff_matchups": playoff_rows,
        "schedule": forecast[["game_id", "week", "gameday", "away_team", "home_team",
                              "home_win_probability"]].to_dict("records"),
        "provenance": {
            "training_seasons": [2021, 2022, 2023, 2024, 2025],
            "feature_history_seasons": list(range(2018, 2026)),
            "temperature_slope": TEMPERATURE_SLOPE, "injuries": "not used",
            "market_lines": "not used", "qb_review": "approved",
        },
    }
    Path("data/operator").mkdir(parents=True, exist_ok=True)
    Path("data/season-runs").mkdir(parents=True, exist_ok=True)
    Path("data/operator/preseason-qb-review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    input_path = Path("data/season-runs/input.json")
    input_path.write_text(json.dumps(input_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    snapshot = run_simulation_snapshot(input_path, Path("data/season-runs/latest.json"))
    summary = sorted(snapshot["teams"], key=lambda row: row["playoff_probability"], reverse=True)
    print(json.dumps({"games": len(forecast), "training_games": len(features), "cutoff": cutoff,
                      "top": summary[:10]}, indent=2))


if __name__ == "__main__":
    main()
