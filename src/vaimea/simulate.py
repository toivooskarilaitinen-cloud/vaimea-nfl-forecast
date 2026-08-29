from __future__ import annotations

import numpy as np
import pandas as pd


def rank_conference(teams, wins, head_to_head, division, conference, point_diff):
    """Deterministic approximation of NFL order; flags unsupported multi-team edge cases upstream."""
    return sorted(teams,key=lambda t:(wins[t], head_to_head.get(t,0), division.get(t,0), conference.get(t,0), point_diff.get(t,0),t),reverse=True)

def simulate(schedule: pd.DataFrame, team_meta: pd.DataFrame, n=100000, seed=1, batch_size=5000) -> dict:
    """Simulate seasons in bounded vectorized batches."""
    if n <= 0 or batch_size <= 0:
        raise ValueError("n and batch_size must be positive")

    rng = np.random.default_rng(seed)
    teams = sorted(set(schedule.home_team) | set(schedule.away_team))
    team_index = {team: index for index, team in enumerate(teams)}
    meta = team_meta.set_index("team").loc[teams]
    home = schedule.home_team.map(team_index).to_numpy(dtype=np.int16)
    away = schedule.away_team.map(team_index).to_numpy(dtype=np.int16)
    probability = schedule.home_win_probability.to_numpy(dtype=float)
    conferences = meta.conference.to_numpy()
    divisions = meta.division.to_numpy()
    same_conference = conferences[home] == conferences[away]
    same_division = divisions[home] == divisions[away]
    expected = np.zeros(len(teams), dtype=np.int64)
    playoff_counts = np.zeros(len(teams), dtype=np.int64)

    for start in range(0, n, batch_size):
        batch = min(batch_size, n - start)
        home_wins = rng.random((batch, len(schedule))) < probability
        winners = np.where(home_wins, home, away)
        losers = np.where(home_wins, away, home)
        rows = np.broadcast_to(np.arange(batch)[:, None], winners.shape)
        wins = np.zeros((batch, len(teams)), dtype=np.int16)
        division_wins = np.zeros_like(wins)
        conference_wins = np.zeros_like(wins)
        point_diff = np.zeros_like(wins)
        np.add.at(wins, (rows, winners), 1)
        np.add.at(point_diff, (rows, winners), 1)
        np.add.at(point_diff, (rows, losers), -1)
        np.add.at(conference_wins, (rows[:, same_conference], winners[:, same_conference]), 1)
        np.add.at(division_wins, (rows[:, same_division], winners[:, same_division]), 1)

        # Mixed-radix encoding preserves rank_conference's lexicographic order.
        score = wins.astype(np.int64)
        for value, radix in ((wins, 20), (division_wins, 20), (conference_wins, 20)):
            score = score * radix + value
        score = (score * 40 + point_diff + 20) * 40 + np.arange(len(teams))
        selected = np.zeros((batch, len(teams)), dtype=bool)
        for conference in pd.unique(conferences):
            conference_ids = np.flatnonzero(conferences == conference)
            for division in pd.unique(divisions[conference_ids]):
                division_ids = conference_ids[divisions[conference_ids] == division]
                champion = division_ids[np.argmax(score[:, division_ids], axis=1)]
                selected[np.arange(batch), champion] = True
            wild_score = score[:, conference_ids].copy()
            wild_score[selected[:, conference_ids]] = -1
            wild_local = np.argpartition(wild_score, -3, axis=1)[:, -3:]
            selected[np.arange(batch)[:, None], conference_ids[wild_local]] = True
        expected += wins.sum(axis=0)
        playoff_counts += selected.sum(axis=0)

    return {
        team: {
            "expected_wins": expected[index] / n,
            "playoff_probability": playoff_counts[index] / n,
        }
        for index, team in enumerate(teams)
    }
