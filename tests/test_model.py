import numpy as np
import pandas as pd

from vaimea.model import walk_forward


def test_walk_forward_is_strictly_past_only():
    rng=np.random.default_rng(4); rows=[]
    for season in range(2019,2025):
        for _ in range(80):
            x=rng.normal(); p=1/(1+np.exp(-x)); rows.append({"season":season,"strength_diff":x,"qb_diff":0.,"home_field":1.,"rest_diff":0.,"home_win":rng.random()<p})
    pred,metrics=walk_forward(pd.DataFrame(rows),2021)
    assert set(pred.season)=={2021,2022,2023,2024}; assert 0<=metrics["brier"]<=1

