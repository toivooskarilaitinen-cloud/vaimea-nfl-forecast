from __future__ import annotations

import json
from pathlib import Path


def build_history(ledger: Path, public: Path) -> None:
    entries=[]
    for f in sorted(ledger.glob("*.json")):
        x=json.loads(f.read_text(encoding="utf-8")); entries.append(x)
    latest=entries[-1] if entries else {"forecasts":[]}; previous=entries[-2] if len(entries)>1 else {"forecasts":[]}
    old={x["game_id"]:x.get("home_win_probability") for x in previous["forecasts"]}
    movers=[dict(x,move=(x.get("home_win_probability")-old[x["game_id"]])) for x in latest["forecasts"] if x["game_id"] in old]
    public.mkdir(parents=True,exist_ok=True)
    for name,value in [("latest.json",latest),("history.json",entries),("movers.json",sorted(movers,key=lambda x:abs(x["move"]),reverse=True))]:
        (public/name).write_text(json.dumps(value,indent=2,default=str)+"\n",encoding="utf-8")

