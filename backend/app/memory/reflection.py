"""
Detecting patterns in the agent's own recent coverage.

Deduplication asks "have I said this before?". This asks a different question:
"looking back at what I've published, is there a pattern I should acknowledge?"

The detection is deterministic. The model is told what the pattern is and asked to
write about it - it is never asked to find a trend, because a model asked whether it
sees a pattern will always say yes.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from sqlalchemy.orm import Session

from backend.app.memory.models import PostModel
from backend.app.memory.embeddings import embed

logger = logging.getLogger("autonomous_agent.memory.reflection")

# Posts required before reflecting at all - below this there is no body of work.
MIN_POSTS_BEFORE_REFLECTING = 5

# Window of recent posts examined for a pattern.
REFLECTION_WINDOW = 5

# How many of that window must be mutually related to count as a trend.
MIN_POSTS_IN_TREND = 3

# Cosine distance below which two posts count as covering related ground. Looser than
# duplicate detection - these are different posts on adjacent subjects. Calibrated on
# measured pairs: posts within one subfield (self-critique reasoning, step
# verification, process reward models) sat at 0.56-0.75, while unrelated pairs
# (reasoning vs sparse attention vs quantisation) sat at 0.82-0.99. Grouping is
# anchor-based, so a theme forms when one post is close to several others rather
# than requiring every pair to be mutually close.
TREND_DISTANCE = 0.70

# Ordinary posts that must follow a reflection before another is allowed.
POSTS_BETWEEN_REFLECTIONS = 5


@dataclass
class CoverageTrend:
    """A recurring theme across the agent's recent posts."""
    titles: List[str]
    sources: List[str]
    window_size: int

    @property
    def count(self) -> int:
        return len(self.titles)


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) or 1.0) * (np.linalg.norm(b) or 1.0)
    return 1.0 - float(a @ b) / float(denom)


def detect_coverage_trend(db: Session, agent_id: str) -> Optional[CoverageTrend]:
    """
    Return the dominant theme across recent posts, or None if there isn't one.

    None is the common and correct answer: a varied feed has no trend worth
    remarking on, and a reflection post with nothing to observe is filler.
    """
    posts = (
        db.query(PostModel)
        .filter(PostModel.agent_id == agent_id)
        .order_by(PostModel.created_at.desc())
        .limit(REFLECTION_WINDOW)
        .all()
    )
    if len(posts) < MIN_POSTS_BEFORE_REFLECTING:
        return None

    # Pace reflections: require a run of ordinary posts since the last one.
    recent_kinds = [getattr(p, "kind", "topic") or "topic" for p in posts]
    if "reflection" in recent_kinds[:POSTS_BETWEEN_REFLECTIONS]:
        return None

    try:
        vectors = [np.array(embed(f"{p.topic_title or ''} {p.text}")) for p in posts]
    except Exception as err:
        logger.debug(f"Trend detection skipped, embeddings unavailable: {err}")
        return None

    # The largest group of mutually related posts wins.
    best: List[int] = []
    for i in range(len(posts)):
        group = [i] + [
            j for j in range(len(posts))
            if j != i and _cosine_distance(vectors[i], vectors[j]) <= TREND_DISTANCE
        ]
        if len(group) > len(best):
            best = group

    if len(best) < MIN_POSTS_IN_TREND:
        return None

    import json

    titles, sources = [], []
    for idx in sorted(best):
        post = posts[idx]
        titles.append(post.topic_title or "(untitled)")
        try:
            sources.extend(json.loads(post.sources_json or "[]"))
        except Exception:
            pass

    logger.info(
        "Coverage trend detected: %d of the last %d posts cover related ground.",
        len(titles), len(posts)
    )
    return CoverageTrend(titles=titles, sources=sources, window_size=len(posts))
