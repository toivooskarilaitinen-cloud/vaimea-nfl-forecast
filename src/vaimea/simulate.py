from __future__ import annotations

import numpy as np
import pandas as pd


def rank_conference(teams, wins, head_to_head, division, conference, point_diff):
    """Deterministic approximation of NFL order; flags unsupported multi-team edge cases upstream."""
    return sorted(teams,key=lambda t:(wins[t], head_to_head.get(t,0), division.get(t,0), conference.get(t,0), point_diff.get(t,0),t),reverse=True)

def _matchup_matrices(matchups, teams, team_index):
    if matchups is None:
        return None
    required = {
        "home_team", "away_team", "home_win_probability",
        "bye_home_win_probability", "neutral_win_probability",
    }
    missing = required - set(matchups.columns)
    if missing:
        raise ValueError(f"playoff matchups missing columns: {sorted(missing)}")
    size = len(teams)
    home = np.full((size, size), np.nan)
    bye = np.full((size, size), np.nan)
    neutral = np.full((size, size), np.nan)
    for row in matchups.itertuples():
        i, j = team_index[row.home_team], team_index[row.away_team]
        home[i, j] = float(row.home_win_probability)
        bye[i, j] = float(row.bye_home_win_probability)
        neutral[i, j] = float(row.neutral_win_probability)
    mask = ~np.eye(size, dtype=bool)
    if any(np.isnan(matrix[mask]).any() for matrix in (home, bye, neutral)):
        raise ValueError("playoff matchup matrix must contain every ordered team pair")
    if any(((matrix[mask] < 0) | (matrix[mask] > 1)).any() for matrix in (home, bye, neutral)):
        raise ValueError("playoff matchup probabilities must be between zero and one")
    return home, bye, neutral


def _play_game(home, away, probability_matrix, draws):
    probability = probability_matrix[home, away]
    return np.where(draws < probability, home, away)


def simulate(
    schedule: pd.DataFrame,
    team_meta: pd.DataFrame,
    n=100000,
    seed=1,
    batch_size=5000,
    playoff_matchups: pd.DataFrame | None = None,
) -> dict:
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
    division_counts = np.zeros(len(teams), dtype=np.int64)
    conference_counts = np.zeros(len(teams), dtype=np.int64)
    super_bowl_counts = np.zeros(len(teams), dtype=np.int64)
    matchup_matrices = _matchup_matrices(playoff_matchups, teams, team_index)
    # A separate fixed-size stream keeps results identical across batch sizes.
    playoff_draws = np.random.default_rng(seed + 1).random((n, 13)) if matchup_matrices else None

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
        division_champions = np.zeros((batch, len(teams)), dtype=bool)
        seeds_by_conference = []
        for conference in pd.unique(conferences):
            conference_ids = np.flatnonzero(conferences == conference)
            champions = []
            for division in pd.unique(divisions[conference_ids]):
                division_ids = conference_ids[divisions[conference_ids] == division]
                champion = division_ids[np.argmax(score[:, division_ids], axis=1)]
                selected[np.arange(batch), champion] = True
                division_champions[np.arange(batch), champion] = True
                champions.append(champion)
            champions = np.column_stack(champions)
            champion_scores = np.take_along_axis(score, champions, axis=1)
            champion_order = np.argsort(champion_scores, axis=1)[:, ::-1]
            seeded_champions = np.take_along_axis(champions, champion_order, axis=1)
            wild_score = score[:, conference_ids].copy()
            wild_score[selected[:, conference_ids]] = -1
            wild_local = np.argpartition(wild_score, -3, axis=1)[:, -3:]
            wild_teams = conference_ids[wild_local]
            wild_scores = np.take_along_axis(score, wild_teams, axis=1)
            wild_order = np.argsort(wild_scores, axis=1)[:, ::-1]
            seeded_wild = np.take_along_axis(wild_teams, wild_order, axis=1)
            selected[np.arange(batch)[:, None], seeded_wild] = True
            seeds_by_conference.append(np.column_stack([seeded_champions, seeded_wild]))

        if matchup_matrices:
            home_matrix, bye_matrix, neutral_matrix = matchup_matrices
            draw = playoff_draws[start:start + batch]
            conference_winners = []
            for conference_number, seeds in enumerate(seeds_by_conference):
                wc_offset = conference_number * 3
                wc_teams = []
                wc_seed_numbers = []
                for game_number, (home_seed, away_seed) in enumerate(((1, 6), (2, 5), (3, 4))):
                    winner = _play_game(
                        seeds[:, home_seed], seeds[:, away_seed], home_matrix,
                        draw[:, wc_offset + game_number],
                    )
                    wc_teams.append(winner)
                    wc_seed_numbers.append(
                        np.where(winner == seeds[:, home_seed], home_seed + 1, away_seed + 1)
                    )
                wc_teams = np.column_stack(wc_teams)
                wc_seed_numbers = np.column_stack(wc_seed_numbers)
                lowest_index = np.argmax(wc_seed_numbers, axis=1)
                lowest_team = np.take_along_axis(wc_teams, lowest_index[:, None], axis=1)[:, 0]
                lowest_seed = np.take_along_axis(
                    wc_seed_numbers, lowest_index[:, None], axis=1
                )[:, 0]
                divisional_one = _play_game(
                    seeds[:, 0], lowest_team, bye_matrix, draw[:, 6 + conference_number * 2]
                )
                keep = np.arange(3)[None, :] != lowest_index[:, None]
                other_teams = wc_teams[keep].reshape(batch, 2)
                other_seeds = wc_seed_numbers[keep].reshape(batch, 2)
                order = np.argsort(other_seeds, axis=1)
                other_teams = np.take_along_axis(other_teams, order, axis=1)
                other_seeds = np.take_along_axis(other_seeds, order, axis=1)
                divisional_two = _play_game(
                    other_teams[:, 0], other_teams[:, 1], home_matrix,
                    draw[:, 7 + conference_number * 2],
                )
                divisional_two_seed = np.where(
                    divisional_two == other_teams[:, 0], other_seeds[:, 0], other_seeds[:, 1]
                )
                divisional_one_seed = np.where(divisional_one == seeds[:, 0], 1, lowest_seed)
                first_is_home = divisional_one_seed < divisional_two_seed
                championship_home = np.where(first_is_home, divisional_one, divisional_two)
                championship_away = np.where(first_is_home, divisional_two, divisional_one)
                conference_winner = _play_game(
                    championship_home, championship_away, home_matrix,
                    draw[:, 10 + conference_number],
                )
                conference_winners.append(conference_winner)
                np.add.at(conference_counts, conference_winner, 1)
            super_bowl_winner = _play_game(
                conference_winners[0], conference_winners[1], neutral_matrix, draw[:, 12]
            )
            np.add.at(super_bowl_counts, super_bowl_winner, 1)
        expected += wins.sum(axis=0)
        playoff_counts += selected.sum(axis=0)
        division_counts += division_champions.sum(axis=0)

    return {
        team: {
            "expected_wins": expected[index] / n,
            "playoff_probability": playoff_counts[index] / n,
            "division_probability": division_counts[index] / n,
            "conference_probability": (
                conference_counts[index] / n if matchup_matrices else None
            ),
            "super_bowl_probability": (
                super_bowl_counts[index] / n if matchup_matrices else None
            ),
        }
        for index, team in enumerate(teams)
    }
