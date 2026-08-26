from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = ["strength_diff", "qb_diff", "home_field", "rest_diff"]


class RegularizedLogit:
    def __init__(self, weights: np.ndarray, mean: np.ndarray, scale: np.ndarray):
        self.weights, self.mean, self.scale = weights, mean, scale

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        z = np.c_[np.ones(len(x)), (x.to_numpy(float) - self.mean) / self.scale] @ self.weights
        p = 1 / (1 + np.exp(-np.clip(z, -35, 35)))
        return np.c_[1 - p, p]

def fit(train: pd.DataFrame, c=.25):
    x = train[FEATURES].to_numpy(float)
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1
    x = np.c_[np.ones(len(x)), (x - mean) / scale]
    y = train.home_win.to_numpy(float)
    w = np.zeros(x.shape[1])
    penalty = 1 / max(c, 1e-9)
    for _ in range(2000):
        p = 1 / (1 + np.exp(-np.clip(x @ w, -35, 35)))
        grad = x.T @ (p - y) / len(y)
        grad[1:] += penalty * w[1:] / len(y)
        new = w - 0.2 * grad
        if np.max(np.abs(new - w)) < 1e-9:
            w = new
            break
        w = new
    return RegularizedLogit(w, mean, scale)


def _brier(y, p):
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def _log_loss(y, p):
    p = np.clip(np.asarray(p), 1e-15, 1 - 1e-15)
    y = np.asarray(y)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

def walk_forward(df: pd.DataFrame, first_test_season: int) -> tuple[pd.DataFrame,dict]:
    preds=[]
    for season in sorted(s for s in df.season.unique() if s>=first_test_season):
        train=df[df.season<season]; test=df[df.season==season].copy()
        if len(train)<100 or test.empty: continue
        test["probability"]=fit(train).predict_proba(test[FEATURES])[:,1]; preds.append(test)
    p=pd.concat(preds,ignore_index=True)
    y=p.home_win.to_numpy(); prob=p.probability.to_numpy(); base=np.repeat(y.mean(),len(y))
    bins=pd.cut(prob,np.linspace(0,1,11),include_lowest=True)
    cal=p.assign(bin=bins).groupby("bin",observed=True).agg(n=("home_win","size"),predicted=("probability","mean"),observed=("home_win","mean")).reset_index().astype({"bin":"string"})
    metrics={"n":len(p),"brier":_brier(y,prob),"log_loss":_log_loss(y,prob),"accuracy":float(((prob>=.5)==y).mean()),"constant_base_brier":_brier(y,base),"constant_base_log_loss":_log_loss(y,base),"calibration":cal.to_dict("records")}
    return p,metrics

def write_ledger(rows: pd.DataFrame, root: Path, model_version: str, cutoff: str) -> Path:
    root.mkdir(parents=True,exist_ok=True); path=root/f"{cutoff.replace(':','-')}_{model_version}.json"
    if path.exists(): raise FileExistsError("forecast ledger is append-only")
    payload={"model_version":model_version,"cutoff":cutoff,"forecasts":rows.to_dict("records")}
    path.write_text(json.dumps(payload,indent=2,default=str)+"\n",encoding="utf-8"); return path
