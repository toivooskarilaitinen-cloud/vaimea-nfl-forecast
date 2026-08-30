import pandas as pd

from vaimea.simulate import simulate


def _league():
    teams = [f"T{i:02d}" for i in range(16)]
    meta = pd.DataFrame(
        {
            "team": teams,
            "conference": ["A"] * 8 + ["N"] * 8,
            "division": [f"{conference}{division}" for conference in "AN" for division in range(2) for _ in range(4)],
        }
    )
    schedule = pd.DataFrame(
        [
            {
                "home_team": team,
                "away_team": teams[(index + game + 1) % len(teams)],
                "home_win_probability": 0.45 + (game % 3) * 0.1,
            }
            for index, team in enumerate(teams)
            for game in range(6)
        ]
    )
    return schedule, meta


def test_simulation_is_reproducible_across_batch_sizes():
    schedule, meta = _league()
    small_batches = simulate(schedule, meta, n=250, seed=42, batch_size=17)
    one_batch = simulate(schedule, meta, n=250, seed=42, batch_size=250)
    assert small_batches == one_batch


def test_simulation_probabilities_and_expected_wins_are_valid():
    schedule, meta = _league()
    result = simulate(schedule, meta, n=500, seed=7, batch_size=100)
    assert set(result) == set(meta.team)
    assert all(0 <= row["playoff_probability"] <= 1 for row in result.values())
    assert all(0 <= row["division_probability"] <= 1 for row in result.values())
    assert all(row["conference_probability"] is None for row in result.values())
    assert all(row["super_bowl_probability"] is None for row in result.values())
    assert all(0 <= row["expected_wins"] <= 12 for row in result.values())


def test_simulation_rejects_non_positive_draw_count():
    schedule, meta = _league()
    try:
        simulate(schedule, meta, n=0)
    except ValueError as error:
        assert "positive" in str(error)
    else:
        raise AssertionError("simulate should reject n=0")
