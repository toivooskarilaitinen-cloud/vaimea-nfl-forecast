# Data schema

## Official forecast (required)

`game_id`, `season`, `week`, `kickoff`, `home_team`, `away_team`, `home_win_probability`, `cutoff`, `model_version`, `feature_version`, `input_hashes`, `home_qb_id`, `away_qb_id`, `starter_source`, `created_at`, `warnings`.

Probabilities must be finite and in `[0,1]`; cutoff must precede kickoff; `(game_id, model_version, cutoff)` is unique. Timestamps are UTC ISO-8601. Team identifiers use the nflverse canonical abbreviation for that season.

## Starter override

CSV columns: `game_id,team,player_id,announced_at,source_url,reviewed_by`. `announced_at < cutoff` is mandatory. Missing/ambiguous starters fall back to a league-average QB and emit a warning; they are never guessed from future snaps.

