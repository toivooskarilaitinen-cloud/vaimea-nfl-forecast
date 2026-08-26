from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd


def rank_conference(teams, wins, head_to_head, division, conference, point_diff):
    """Deterministic approximation of NFL order; flags unsupported multi-team edge cases upstream."""
    return sorted(teams,key=lambda t:(wins[t], head_to_head.get(t,0), division.get(t,0), conference.get(t,0), point_diff.get(t,0),t),reverse=True)

def simulate(schedule: pd.DataFrame, team_meta: pd.DataFrame, n=20000, seed=1) -> dict:
    rng=np.random.default_rng(seed); teams=sorted(set(schedule.home_team)|set(schedule.away_team)); meta=team_meta.set_index("team")
    counts={t:defaultdict(int) for t in teams}; expected={t:0. for t in teams}
    for _ in range(n):
        wins={t:0 for t in teams}; h2h={t:0 for t in teams}; div={t:0 for t in teams}; conf={t:0 for t in teams}; pdiff={t:0 for t in teams}
        for g in schedule.itertuples():
            home = g.home_team if rng.random()<g.home_win_probability else g.away_team; loser=g.away_team if home==g.home_team else g.home_team
            wins[home]+=1; h2h[home]+=1; pdiff[home]+=1; pdiff[loser]-=1
            if meta.loc[home,"conference"]==meta.loc[loser,"conference"]: conf[home]+=1
            if meta.loc[home,"division"]==meta.loc[loser,"division"]: div[home]+=1
        playoff=[]
        for c in meta.conference.unique():
            ct=[t for t in teams if meta.loc[t,"conference"]==c]; champs=[]
            for d in meta[meta.conference==c].division.unique():
                champs.append(rank_conference([t for t in ct if meta.loc[t,"division"]==d],wins,h2h,div,conf,pdiff)[0])
            wild=rank_conference([t for t in ct if t not in champs],wins,h2h,div,conf,pdiff)[:3]
            playoff += champs+wild
        for t in teams:
            expected[t]+=wins[t]; counts[t]["playoffs"]+=t in playoff
        # Bracket strength is represented by supplied game probabilities in v0.1; title rounds are intentionally not fabricated.
    return {t:{"expected_wins":expected[t]/n,"playoff_probability":counts[t]["playoffs"]/n} for t in teams}

