from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from .io import atomic_json
from .simulate import simulate

PROBABILITY_FIELDS = (
    "playoff_probability",
    "division_probability",
    "conference_probability",
    "super_bowl_probability",
)


def run_simulation_snapshot(source: Path, output: Path) -> dict | None:
    """Run the frozen season simulator from a versioned, as-of input package."""
    if not source.exists():
        return None
    payload = json.loads(source.read_text(encoding="utf-8"))
    required = {"season", "week", "as_of", "model_version", "schedule", "team_meta"}
    missing = required - payload.keys()
    if missing:
        raise ValueError(f"season simulation input missing fields: {sorted(missing)}")
    n = int(payload.get("simulation_count", 100000))
    seed = int(payload.get("random_seed", 20260826))
    results = simulate(
        pd.DataFrame(payload["schedule"]),
        pd.DataFrame(payload["team_meta"]),
        n=n,
        seed=seed,
    )
    snapshot = {
        "season": int(payload["season"]),
        "week": payload["week"],
        "as_of": payload["as_of"],
        "model_version": payload["model_version"],
        "simulation_count": n,
        "random_seed": seed,
        "tiebreaker_mode": payload.get("tiebreaker_mode", "approximation_v0.1"),
        "teams": [dict(team=team, **values) for team, values in sorted(results.items())],
    }
    _validated_snapshot(snapshot)
    atomic_json(output, snapshot)
    return snapshot


def _validated_snapshot(payload: dict) -> dict:
    required = {"season", "week", "as_of", "model_version", "simulation_count", "teams"}
    missing = required - payload.keys()
    if missing:
        raise ValueError(f"season snapshot missing fields: {sorted(missing)}")
    if int(payload["simulation_count"]) <= 0:
        raise ValueError("simulation_count must be positive")
    teams = payload["teams"]
    if not isinstance(teams, list) or not teams:
        raise ValueError("season snapshot needs team rows")
    codes = [row.get("team") for row in teams]
    if any(not code for code in codes) or len(codes) != len(set(codes)):
        raise ValueError("team codes must be present and unique")
    for row in teams:
        for field in PROBABILITY_FIELDS:
            value = row.get(field)
            if value is not None and not 0 <= float(value) <= 1:
                raise ValueError(f"{row['team']} {field} must be between zero and one")
    return payload


def _forecast_fingerprint(payload: dict) -> str:
    stable = {
        "season": payload["season"],
        "week": payload["week"],
        "model_version": payload["model_version"],
        "simulation_count": payload["simulation_count"],
        "teams": sorted(payload["teams"], key=lambda row: row["team"]),
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def archive_snapshot(source: Path, ledger_dir: Path) -> Path | None:
    """Append a changed season simulation to an immutable ledger."""
    if not source.exists():
        return None
    payload = _validated_snapshot(json.loads(source.read_text(encoding="utf-8")))
    fingerprint = _forecast_fingerprint(payload)
    for path in ledger_dir.glob("*.json") if ledger_dir.exists() else []:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("forecast_fingerprint") == fingerprint:
            return path
    as_of = datetime.fromisoformat(str(payload["as_of"]))
    if as_of.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    archived = {
        **payload,
        "kind": "season_probability_snapshot",
        "archived_at": datetime.now(UTC).isoformat(),
        "forecast_fingerprint": fingerprint,
    }
    name = f"{as_of.astimezone(UTC):%Y%m%dT%H%M%SZ}_{fingerprint[:12]}.json"
    target = ledger_dir / name
    if target.exists():
        raise FileExistsError(f"immutable season snapshot already exists: {target}")
    atomic_json(target, archived)
    return target


def build_public_history(ledger_dir: Path, output: Path) -> dict:
    snapshots = []
    for path in sorted(ledger_dir.glob("*.json")) if ledger_dir.exists() else []:
        snapshots.append(_validated_snapshot(json.loads(path.read_text(encoding="utf-8"))))
    snapshots.sort(key=lambda row: row["as_of"])
    payload = {
        "kind": "season_probability_history",
        "append_only": True,
        "generated_at": snapshots[-1].get("archived_at") if snapshots else None,
        "snapshots": snapshots,
        "latest": snapshots[-1] if snapshots else None,
        "availability": {
            "playoff_probability": True,
            "division_probability": True,
            "conference_probability": any(
                row.get("conference_probability") is not None
                for snapshot in snapshots
                for row in snapshot["teams"]
            ),
            "super_bowl_probability": any(
                row.get("super_bowl_probability") is not None
                for snapshot in snapshots
                for row in snapshot["teams"]
            ),
        },
    }
    atomic_json(output, payload)
    return payload


def audit_history(ledger_dir: Path) -> dict:
    errors = []
    fingerprints = set()
    for path in sorted(ledger_dir.glob("*.json")) if ledger_dir.exists() else []:
        payload = json.loads(path.read_text(encoding="utf-8"))
        expected = _forecast_fingerprint(_validated_snapshot(payload))
        if payload.get("forecast_fingerprint") != expected:
            errors.append(f"{path.name}: fingerprint mismatch")
        if expected in fingerprints:
            errors.append(f"{path.name}: duplicate forecast fingerprint")
        fingerprints.add(expected)
    return {
        "status": "ok" if not errors else "failed",
        "snapshots": len(fingerprints),
        "errors": errors,
    }
