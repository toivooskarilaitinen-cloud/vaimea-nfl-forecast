from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .season_history import build_public_history


def build_history(ledger: Path, public: Path) -> None:
    entries = []
    for f in sorted(ledger.glob("*.json")):
        entries.append(json.loads(f.read_text(encoding="utf-8")))

    versions: dict[str, list[tuple[str, dict]]] = {}
    for entry in entries:
        stamp = entry.get("approved_at") or entry.get("cutoff") or ""
        for row in entry.get("forecasts", []):
            versions.setdefault(row["game_id"], []).append((stamp, {**row, "snapshot_cutoff": entry.get("cutoff"), "snapshot_approved_at": entry.get("approved_at"), "model_version": entry.get("model_version")}))

    now = datetime.now(UTC).isoformat()
    latest_rows = []
    movers = []
    for game_versions in versions.values():
        game_versions.sort(key=lambda item: item[0])
        latest = dict(game_versions[-1][1])
        final_lock_at = latest.get("final_lock_at")
        latest["lock_status"] = "final" if final_lock_at and now >= final_lock_at else "updateable"
        latest_rows.append(latest)
        if len(game_versions) > 1:
            previous = game_versions[-2][1]
            latest_prob = latest.get("home_win_probability")
            previous_prob = previous.get("home_win_probability")
            if latest_prob is not None and previous_prob is not None:
                movers.append({**latest, "move": latest_prob - previous_prob, "move_reason": latest.get("change_reason", "uusi tuotantoajo")})

    newest_entry = max(entries, key=lambda x: x.get("approved_at") or x.get("cutoff") or "", default={})
    latest_payload = {**newest_entry, "forecasts": sorted(latest_rows, key=lambda row: row.get("kickoff", ""))}
    if not entries:
        latest_payload = {"forecasts": []}

    quality_path = public / "data-quality.json"
    data_quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.exists() else {}
    status = {
        "generated_at": datetime.now(UTC).isoformat(),
        "forecast_status": "official" if entries else "awaiting_first_production_run",
        "data_fetched_at": data_quality.get("checked_at") or newest_entry.get("data_fetched_at"),
        "official_forecast_data_fetched_at": newest_entry.get("data_fetched_at"),
        "source_week": newest_entry.get("source_week") or data_quality.get("summary", {}).get("source_week"),
        "model_version": newest_entry.get("model_version"),
        "cutoff": newest_entry.get("cutoff"),
        "warnings": newest_entry.get("quality", {}).get("warnings", []),
        "ledger_entries": len(entries),
    }
    public.mkdir(parents=True, exist_ok=True)
    for name, value in [
        ("latest.json", latest_payload),
        ("history.json", entries),
        ("movers.json", sorted(movers, key=lambda x: abs(x["move"]), reverse=True)),
        ("status.json", status),
    ]:
        (public / name).write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")
    build_public_history(ledger.parent / "season-forecast-ledger", public / "season-history.json")
