from __future__ import annotations

import pandas as pd


class QualityError(ValueError): pass

def gate_pbp(df: pd.DataFrame) -> dict:
    required={"game_id","season","week","home_team","away_team","posteam","defteam","epa","available_at"}
    missing=required-set(df.columns)
    if missing: raise QualityError(f"missing columns: {sorted(missing)}")
    if df.empty: raise QualityError("empty play-by-play")
    if df["game_id"].isna().any(): raise QualityError("null game_id")
    if df["epa"].dropna().abs().quantile(.999) > 15: raise QualityError("implausible EPA tail")
    bad=(df["posteam"].notna() & df["defteam"].notna() & (df["posteam"]==df["defteam"])).sum()
    if bad: raise QualityError(f"{bad} plays have identical offense and defense")
    dropbacks = df.get("qb_dropback", pd.Series(0, index=df.index)).fillna(0).astype(bool)
    quarterback = df.get("passer_player_id", pd.Series(index=df.index, dtype="object"))
    qb_coverage = float(quarterback[dropbacks].notna().mean()) if dropbacks.any() else 0.0
    return {"rows":len(df),"games":int(df.game_id.nunique()),"epa_null_rate":float(df.epa.isna().mean()),"qb_coverage":qb_coverage}

def assert_asof(df: pd.DataFrame, cutoff: pd.Timestamp) -> None:
    if (pd.to_datetime(df.available_at, utc=True) >= cutoff).any():
        raise QualityError("future information detected at forecast cutoff")


def missing_mature_results(
    games: pd.DataFrame,
    pbp: pd.DataFrame,
    season: int,
    now: pd.Timestamp,
    grace_hours: int = 96,
) -> list[str]:
    """Return completed games old enough that their PBP must already be available."""
    required = {"game_id", "season", "gameday", "home_score", "away_score"}
    missing = required - set(games.columns)
    if missing:
        raise QualityError(f"schedule result data missing columns: {sorted(missing)}")
    cutoff_date = (now - pd.Timedelta(hours=grace_hours)).date()
    frame = games[games.season.eq(season)].copy()
    frame["gameday"] = pd.to_datetime(frame.gameday).dt.date
    mature = frame[
        frame.home_score.notna()
        & frame.away_score.notna()
        & frame.gameday.le(cutoff_date)
    ]
    observed = set(pbp.loc[pbp.season.eq(season), "game_id"].dropna()) if not pbp.empty else set()
    return sorted(set(mature.game_id) - observed)
