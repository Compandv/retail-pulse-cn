"""Resolve a rebase stopped on public/data conflicts; exit 1 to let the caller abort.

Used by scripts/sync_data.ps1 when the local data commit is replayed on top of a
GitHub commit (typically the cloud fallback collected the same day). Whole files
are chosen, never merged line by line, so every JSON file stays valid:
- index files (a "dates" or "weeks" list): union of both lists, other keys local;
- snapshots carrying meta.tradeDate or meta.week: the newer one, local on a tie
  (the local run also keeps model wording and private captures);
- anything else: the local version.
During a rebase, stage 2 is GitHub's side and stage 3 the local commit being replayed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, encoding="utf-8")
    if check and result.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def stage(path: str, number: int) -> bytes | None:
    result = subprocess.run(["git", "-C", str(ROOT), "show", f":{number}:{path}"], capture_output=True)
    return result.stdout if result.returncode == 0 else None


def parse(raw: bytes | None) -> dict | None:
    try:
        value = json.loads(raw.decode("utf-8-sig")) if raw is not None else None
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def stamp(payload: dict) -> str:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    return str(meta.get("tradeDate") or meta.get("week") or "")


def choose(path: str, remote_raw: bytes | None, local_raw: bytes | None) -> bytes:
    """The bytes to keep. A whole side is kept verbatim so its formatting does not churn."""
    remote, local = parse(remote_raw), parse(local_raw)
    if remote is None or local is None:
        if local is None and remote is None:
            raise RuntimeError(f"{path}: 两边都不是有效 JSON")
        return local_raw if local is not None else remote_raw
    for key in ("dates", "weeks"):
        if isinstance(local.get(key), list) and isinstance(remote.get(key), list):
            if set(remote[key]) <= set(local[key]):
                return local_raw
            merged = {**local, key: sorted(set(local[key]) | set(remote[key]))}
            return json.dumps(merged, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return remote_raw if stamp(remote) > stamp(local) else local_raw


def resolve() -> list[str]:
    conflicted = [p for p in git("diff", "--name-only", "--diff-filter=U").splitlines() if p]
    if not conflicted:
        raise RuntimeError("没有待解决的冲突")
    outside = [p for p in conflicted if not p.startswith("public/data/")]
    if outside:
        raise RuntimeError("冲突不只在 public/data：" + "、".join(outside))
    for path in conflicted:
        if not path.endswith(".json"):
            raise RuntimeError(f"{path}: 不是 JSON，无法自动选择")
        target = ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(choose(path, stage(path, 2), stage(path, 3)))
        git("add", "--", path)
    return conflicted


def main(argv=None) -> int:
    global ROOT
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        ROOT = Path(argv[0]).resolve()  # the repository; defaults to this project
    try:
        files = resolve()
    except RuntimeError as exc:
        print(f"未自动解决：{exc}", file=sys.stderr)
        return 1
    print(f"已自动解决 {len(files)} 个数据文件冲突")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
