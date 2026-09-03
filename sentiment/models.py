from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Post:
    source: str
    target_id: str
    target_name: str
    text: str
    published_at: datetime
    author_key: str


@dataclass(frozen=True)
class CollectionOutcome:
    source: str
    target_id: str
    ok: bool
    posts: tuple[Post, ...] = ()
    raw_count: int = 0
    error: str = ""


@dataclass(frozen=True)
class Signals:
    novice: float
    fomo: float
    panic: float
    direction: float
    matched: tuple[str, ...]


@dataclass(frozen=True)
class AnalyzedPost:
    post: Post
    signals: Signals
