from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from .io import immutable_parquet

BASE = "https://github.com/nflverse/nflverse-data/releases/download"

def fetch(url: str, target: Path, timeout: int = 120) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists(): return target
    r = requests.get(url, timeout=timeout); r.raise_for_status()
    tmp = target.with_suffix(target.suffix + ".tmp"); tmp.write_bytes(r.content); tmp.replace(target)
    return target

def ingest(root: Path, seasons: list[int], snapshot: str | None = None) -> list[Path]:
    stamp = snapshot or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out=[]
    for season in seasons:
        raw = fetch(f"{BASE}/pbp/play_by_play_{season}.parquet", root/"raw"/stamp/f"pbp_{season}.parquet")
        df = pd.read_parquet(raw)
        cols = [c for c in ["game_id","season","week","game_date","home_team","away_team","posteam","defteam","play_type","epa","cpoe","qb_dropback","passer_player_id","passer_player_name","complete_pass","air_yards","yards_gained"] if c in df]
        clean=df[cols].copy(); clean["available_at"] = pd.to_datetime(clean["game_date"], utc=True) + pd.Timedelta(days=2)
        out.append(immutable_parquet(clean, root/"clean"/stamp/f"pbp_{season}.parquet", str(raw)))
    return out

