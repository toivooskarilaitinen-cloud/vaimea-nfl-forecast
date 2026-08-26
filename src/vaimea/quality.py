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
    return {"rows":len(df),"games":int(df.game_id.nunique()),"epa_null_rate":float(df.epa.isna().mean())}

def assert_asof(df: pd.DataFrame, cutoff: pd.Timestamp) -> None:
    if (pd.to_datetime(df.available_at, utc=True) >= cutoff).any():
        raise QualityError("future information detected at forecast cutoff")

