from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()

def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)

def immutable_parquet(df: pd.DataFrame, path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists(): raise FileExistsError(f"immutable artifact already exists: {path}")
    df.to_parquet(path, index=False)
    atomic_json(path.with_suffix(path.suffix + ".manifest.json"), {
        "created_at": datetime.now(UTC).isoformat(), "source": source,
        "rows": len(df), "columns": list(df.columns), "sha256": sha256(path)})
    return path

