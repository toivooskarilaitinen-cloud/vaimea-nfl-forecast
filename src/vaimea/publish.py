from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .season_history import build_public_history


def build_history(ledger: Path, public: Path) -> None:
    entries=[]
    for f in sorted(ledger.glob("*.json")):
        x=json.loads(f.read_text(encoding="utf-8")); entries.append(x)
    latest=entries[-1] if entries else {"forecasts":[]}; previous=entries[-2] if len(entries)>1 else {"forecasts":[]}
    old={x["game_id"]:x.get("home_win_probability") for x in previous["forecasts"]}
    movers=[dict(x,move=(x.get("home_win_probability")-old[x["game_id"]]),move_reason=x.get("change_reason","uusi tuotantoajo")) for x in latest["forecasts"] if x["game_id"] in old]
    quality_path = public / "data-quality.json"
    data_quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.exists() else {}
    status={
        "generated_at": datetime.now(UTC).isoformat(),
        "forecast_status": latest.get("status", "awaiting_first_production_run"),
        "data_fetched_at": latest.get("data_fetched_at") or data_quality.get("checked_at"),
        "source_week": latest.get("source_week") or data_quality.get("summary", {}).get("source_week"),
        "model_version": latest.get("model_version"),
        "cutoff": latest.get("cutoff"),
        "warnings": latest.get("quality", {}).get("warnings", []),
        "ledger_entries": len(entries),
    }
    public.mkdir(parents=True,exist_ok=True)
    for name,value in [("latest.json",latest),("history.json",entries),("movers.json",sorted(movers,key=lambda x:abs(x["move"]),reverse=True)),("status.json",status)]:
        (public/name).write_text(json.dumps(value,indent=2,default=str)+"\n",encoding="utf-8")
    build_public_history(ledger.parent / "season-forecast-ledger", public / "season-history.json")
