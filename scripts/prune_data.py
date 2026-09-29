"""Apply the public snapshot retention policy; dry run unless --apply.

Keep everything for the newest N trading dates (default 60, the longest
baseline window). For older dates:
- community daily snapshots keep aggregates and history series but drop the
  public post excerpts (scopes[].posts, summary.posts), which are ~90% of size;
- per-board market member details (market/members/<date>/) are removed; the
  board-level market daily snapshot is kept.
Report snapshots and every latest.json are never touched. Removed content stays
in git history and in the private captures under work/.

Private captures under work/ (not published):
- report captures (work/report-observations/<date>.json, ~40 MB a day) older than
  the newest --keep-raw dates are gzip-compressed in place; every reader still
  opens them, so replay and long-form rebuilds keep working;
- same-day retry caches (work/report-cache/<version>/<date>/, work/market-source-cache/<date>/)
  older than the newest --keep-cache dates are deleted.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sentiment.snapshot_store import save_json  # noqa: E402
from sentiment.semantic_agent import run_lock  # noqa: E402

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NOTE = "超出保留期，原帖节选已移除；聚合指标与历史序列保留，原文见 Git 历史或私有采集记录。"


def _dates(paths):
    return sorted(p for p in paths if DATE.match(p.stem if p.is_file() else p.name))


def _size(path: Path) -> int:
    return path.stat().st_size if path.is_file() else sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def slim_community(payload: dict) -> bool:
    """Drop post excerpts in place; return whether anything changed."""
    changed = False
    for scope in payload.get("scopes") or []:
        if scope.get("posts"):
            scope["posts"] = []
            changed = True
    summary = payload.get("summary")
    if isinstance(summary, dict) and summary.get("posts"):
        summary["posts"] = []
        changed = True
    if changed:
        payload.setdefault("meta", {})["postsPruned"] = NOTE
    return changed


def plan_work(root: Path, keep_raw: int, keep_cache: int):
    work = root / "work"
    raw = _dates((work / "report-observations").glob("*.json"))
    caches = [d for base in [*(work / "report-cache").glob("*"), work / "market-source-cache"] if base.is_dir()
              for d in _dates(p for p in base.glob("*") if p.is_dir())[:-keep_cache]]
    return raw[:-keep_raw] if len(raw) > keep_raw else [], caches


def compress(path: Path) -> int:
    """Replace a capture with its .gz; return bytes freed. The original goes only after the copy verifies."""
    packed = path.with_name(path.name + ".gz")
    data = path.read_bytes()
    temporary = packed.with_name(packed.name + ".tmp")
    temporary.write_bytes(gzip.compress(data, 6))
    if gzip.decompress(temporary.read_bytes()) != data:
        temporary.unlink()
        raise RuntimeError(f"压缩校验失败：{path}")
    temporary.replace(packed)
    path.unlink()
    return len(data) - packed.stat().st_size


def plan(root: Path, keep: int):
    data = root / "public/data"
    community = _dates((data / "daily").glob("*.json"))
    members = _dates(p for p in (data / "market/members").glob("*") if p.is_dir())
    old_community = community[:-keep] if len(community) > keep else []
    old_members = members[:-keep] if len(members) > keep else []
    return old_community, old_members


def run(root: Path, keep: int, apply: bool, keep_raw: int = 20, keep_cache: int = 10) -> dict:
    old_community, old_members = plan(root, keep)
    slimmed, freed = [], 0
    for path in old_community:
        payload = json.loads(path.read_text(encoding="utf-8"))
        before = _size(path)
        original = len(json.dumps(payload, ensure_ascii=False, indent=2).encode())
        if not slim_community(payload):
            continue
        slimmed.append(path.stem)
        if apply:
            save_json(path, payload)
            freed += before - _size(path)
        else:
            # Estimate with one serialization format on both sides.
            freed += original - len(json.dumps(payload, ensure_ascii=False, indent=2).encode())
    for directory in old_members:
        freed += _size(directory)
        if apply:
            shutil.rmtree(directory)
    old_raw, old_caches = plan_work(root, keep_raw, keep_cache)
    for path in old_raw:
        # Estimate about one seventh remains after compression.
        freed += compress(path) if apply else _size(path) * 6 // 7
    for directory in old_caches:
        freed += _size(directory)
        if apply:
            shutil.rmtree(directory)
    return {"keepDates": keep, "applied": apply, "communityPostsRemoved": slimmed,
            "memberDetailsRemoved": [p.name for p in old_members],
            "capturesCompressed": [p.stem for p in old_raw],
            "cachesRemoved": [f"{p.parent.name}/{p.name}" for p in old_caches], "bytesFreed": freed}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keep", type=int, default=60, help="newest trading dates kept in full (minimum 60)")
    parser.add_argument("--keep-raw", type=int, default=20, help="newest report captures kept uncompressed (minimum 5)")
    parser.add_argument("--keep-cache", type=int, default=10, help="newest dates of same-day retry caches kept (minimum 3)")
    parser.add_argument("--apply", action="store_true", help="modify files; without it only report the plan")
    args = parser.parse_args(argv)
    if args.keep < 60:
        parser.error("--keep must be at least 60 so historical baselines stay intact")
    if args.keep_raw < 5 or args.keep_cache < 3:
        parser.error("--keep-raw must be at least 5 and --keep-cache at least 3")
    try:
        with run_lock(ROOT / "work/update-lock"):
            result = run(ROOT, args.keep, args.apply, args.keep_raw, args.keep_cache)
    except RuntimeError:
        print("已有更新运行中，请等待完成后再清理。")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.apply and any(result[k] for k in ("communityPostsRemoved", "memberDetailsRemoved", "capturesCompressed", "cachesRemoved")):
        print("以上为预览；确认后加 --apply 执行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
