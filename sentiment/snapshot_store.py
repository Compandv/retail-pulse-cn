"""Read and write the public community snapshots under public/data/."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def load_daily_snapshots(root: Path, limit: int = 60) -> list[dict[str, Any]]:
    """Load daily snapshots written by prior runs.

    The latest snapshot is intentionally not the only source of history: a
    daily file is the durable observation for that session, so rebuilding from
    all files lets a fresh run recover 20/60-day curves after a restart.
    Invalid or partially-written files are skipped safely.
    """
    daily_dir = root / "public" / "data" / "daily"
    snapshots: list[dict[str, Any]] = []
    try:
        paths = sorted(daily_dir.glob("*.json"))
    except OSError:
        return snapshots
    for path in paths:
        payload = load_json(path, None)
        if not isinstance(payload, dict):
            continue
        meta = payload.get("meta")
        trade_date = meta.get("tradeDate") if isinstance(meta, dict) else None
        if not trade_date:
            trade_date = path.stem
        if isinstance(trade_date, str) and trade_date:
            snapshots.append(payload)
    snapshots.sort(key=lambda item: str((item.get("meta") or {}).get("tradeDate") or ""))
    return snapshots[-max(1, limit):]


def save_daily_files(root: Path, snapshot: Mapping[str, Any]) -> None:
    """Persist one immutable-by-date snapshot plus a lightweight date index."""
    day = str((snapshot.get("meta") or {}).get("tradeDate") or "")
    if not day:
        return
    daily_dir = root / "public" / "data" / "daily"
    save_json(daily_dir / f"{day}.json", snapshot)
    index_path = root / "public" / "data" / "index.json"
    previous = load_json(index_path, {})
    previous_dates = previous.get("dates") if isinstance(previous, dict) else []
    if not isinstance(previous_dates, list):
        previous_dates = []
    dates = {str(value) for value in previous_dates if isinstance(value, str)}
    dates.add(day)
    index = {
        "updatedAt": (snapshot.get("meta") or {}).get("generatedAt"),
        "latest": day,
        "methodVersion": (snapshot.get("meta") or {}).get("methodVersion"),
        "dates": sorted(dates)[-60:],
    }
    save_json(index_path, index)
