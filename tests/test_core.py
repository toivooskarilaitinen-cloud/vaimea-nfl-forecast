import json

import pandas as pd
import pytest

from vaimea.features import qb_strength, team_strength
from vaimea.io import immutable_parquet
from vaimea.model import write_ledger
from vaimea.quality import QualityError, assert_asof, gate_pbp


def pbp():
    rows=[]
    for i in range(12):
        for offense,defense,epa in [("A","B",.2),("B","A",-.1)]:
            rows.append({
                "game_id": f"g{i}", "season": 2025, "week": i + 1,
                "home_team": "A", "away_team": "B", "posteam": offense,
                "defteam": defense, "epa": epa, "cpoe": 3.0, "qb_dropback": 1,
                "passer_player_id": offense, "passer_player_name": offense,
                "available_at": "2025-01-01",
            })
    return pd.DataFrame(rows)

def test_strength_direction_and_center():
    s=team_strength(pbp(),prior_plays=1); a=s.set_index("team")
    assert a.loc["A","offense_epa_adj"] > a.loc["B","offense_epa_adj"]
    assert abs(s.offense_epa_adj.mean())<1e-10

def test_qb_shrinkage():
    q=qb_strength(pbp(),prior_dropbacks=180); assert q.qb_rating.abs().max()<.2

def test_quality_and_asof():
    d=pbp(); assert gate_pbp(d)["games"]==12
    with pytest.raises(QualityError): assert_asof(d,pd.Timestamp("2024-12-31",tz="UTC"))

def test_immutable_artifacts(tmp_path, monkeypatch):
    # The contract is immutability + manifesting; parquet integration runs on Linux CI.
    monkeypatch.setattr(pd.DataFrame, "to_parquet", lambda self, path, index: path.write_bytes(b"PAR1"))
    p=tmp_path/"x.parquet"; immutable_parquet(pbp(),p,"test")
    with pytest.raises(FileExistsError): immutable_parquet(pbp(),p,"test")

def test_ledger_is_append_only(tmp_path):
    r=pd.DataFrame([{"game_id":"g","home_win_probability":.6}]); p=write_ledger(r,tmp_path,"0.1","2026-01-01T00:00:00Z")
    assert json.loads(p.read_text())["model_version"]=="0.1"
    with pytest.raises(FileExistsError): write_ledger(r,tmp_path,"0.1","2026-01-01T00:00:00Z")
