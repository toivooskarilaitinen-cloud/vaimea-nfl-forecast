from __future__ import annotations

import numpy as np
import pandas as pd


def _weighted_mean(x, w):
    ok=np.isfinite(x); return float(np.average(x[ok], weights=w[ok])) if ok.any() else 0.0

def team_strength(pbp: pd.DataFrame, half_life_games=8.0, prior_plays=350, iterations=12) -> pd.DataFrame:
    p=pbp.loc[pbp.posteam.notna() & pbp.defteam.notna() & pbp.epa.notna()].copy()
    games=p[["game_id"]].drop_duplicates().reset_index(drop=True); games["gidx"]=range(len(games))
    p=p.merge(games,on="game_id"); newest=p.gidx.max(); p["w"]=np.power(.5,(newest-p.gidx)/half_life_games)
    league=_weighted_mean(p.epa.to_numpy(),p.w.to_numpy()); teams=sorted(set(p.posteam)|set(p.defteam))
    off={t:0. for t in teams}; deff={t:0. for t in teams}
    for _ in range(iterations):
        for t in teams:
            q=p[p.posteam==t]; raw=_weighted_mean((q.epa-q.defteam.map(deff)).to_numpy(),q.w.to_numpy())-league
            n=q.w.sum(); off[t]=raw*n/(n+prior_plays)
        for t in teams:
            q=p[p.defteam==t]; raw=-(_weighted_mean((q.epa-q.posteam.map(off)).to_numpy(),q.w.to_numpy())-league)
            n=q.w.sum(); deff[t]=raw*n/(n+prior_plays)
        center=np.mean(list(off.values())); off={k:v-center for k,v in off.items()}
        center=np.mean(list(deff.values())); deff={k:v-center for k,v in deff.items()}
    return pd.DataFrame({"team":teams,"offense_epa_adj":[off[t] for t in teams],"defense_epa_adj":[deff[t] for t in teams]})

def qb_strength(pbp: pd.DataFrame, prior_dropbacks=180, epa_weight=.75, cpoe_weight=.25) -> pd.DataFrame:
    q=pbp.loc[(pbp.qb_dropback==1)&pbp.passer_player_id.notna()].copy()
    league_epa=q.epa.mean(); league_cpoe=q.cpoe.mean(); g=q.groupby(["passer_player_id","passer_player_name"],dropna=False)
    out=g.agg(dropbacks=("epa","size"),epa=("epa","mean"),cpoe=("cpoe","mean")).reset_index()
    s=out.dropbacks/(out.dropbacks+prior_dropbacks)
    out["qb_rating"]=s*(epa_weight*(out.epa-league_epa)+cpoe_weight*((out.cpoe-league_cpoe)/10))
    return out.sort_values("qb_rating",ascending=False)

def game_context(schedule: pd.DataFrame) -> pd.DataFrame:
    s=schedule.sort_values("gameday").copy(); last={}; rows=[]
    for r in s.itertuples():
        d=pd.Timestamp(r.gameday); hr=(d-last.get(r.home_team,d-pd.Timedelta(days=7))).days; ar=(d-last.get(r.away_team,d-pd.Timedelta(days=7))).days
        # Keep neutral-site games in every other feature. Only the home-field
        # component is switched off for them.
        location = str(getattr(r,"location","Home")).strip().lower()
        rows.append({"game_id":r.game_id,"home_field":0 if location=="neutral" else 1,"rest_diff":np.clip(hr-ar,-7,7)})
        last[r.home_team]=last[r.away_team]=d
    return pd.DataFrame(rows)
