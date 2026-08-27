import numpy as np
import pandas as pd

from vaimea.features import game_context
from vaimea.model import FEATURES, fit, walk_forward


def test_walk_forward_is_strictly_past_only():
    rng=np.random.default_rng(4); rows=[]
    for season in range(2019,2025):
        for _ in range(80):
            x=rng.normal(); p=1/(1+np.exp(-x)); rows.append({"season":season,"strength_diff":x,"qb_diff":0.,"home_field":1.,"rest_diff":0.,"home_win":rng.random()<p})
    pred,metrics=walk_forward(pd.DataFrame(rows),2021)
    assert set(pred.season)=={2021,2022,2023,2024}; assert 0<=metrics["brier"]<=1


def test_neutral_site_is_exactly_symmetric_and_home_is_not():
    rows=[]
    for i in range(200):
        rows.append({"strength_diff":0.,"qb_diff":0.,"home_field":1.,"rest_diff":0.,"home_win":i<140})
    model=fit(pd.DataFrame(rows))
    neutral=pd.DataFrame([[0.,0.,0.,0.]],columns=FEATURES)
    home=pd.DataFrame([[0.,0.,1.,0.]],columns=FEATURES)
    assert model.predict_proba(neutral)[0,1] == .5
    assert model.predict_proba(home)[0,1] > .5


def test_neutral_site_only_switches_off_home_field():
    schedule=pd.DataFrame([
        {"game_id":"home","gameday":"2025-09-01","home_team":"A","away_team":"B","location":"Home"},
        {"game_id":"neutral","gameday":"2025-09-08","home_team":"A","away_team":"B","location":"Neutral"},
    ])
    context=game_context(schedule).set_index("game_id")
    assert context.loc["home","home_field"] == 1
    assert context.loc["neutral","home_field"] == 0
