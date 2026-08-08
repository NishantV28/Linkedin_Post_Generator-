"""
Cheap, deterministic triage applied before any LLM sees a candidate.

The editorial judge costs one API call per candidate, and a live cycle discovers ~27.
Most of them are structurally incapable of clearing a research persona's bar - forum
threads asking for advice, repositories with a one-line description, years-old blog
posts - and the judge rejected them every time at full price.

This filter drops what cannot pass and caps how many survivors are evaluated, so the
LLM budget is spent on plausible candidates. It deliberately makes no editorial
judgement of its own: it only removes candidates the persona's own thresholds already
exclude, and orders the rest so the most promising are seen first.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from backend.app.agent.persona.schema import PersonaConfig
from backend.app.agent.tools.schema import TopicCandidate

logger = logging.getLogger("autonomous_agent.tools.prefilter")

# Anything older than this cannot be "news" for any persona.
MAX_CANDIDATE_AGE_DAYS = 30

# Upper bound on candidates evaluated per cycle, so token cost stays predictable.
MAX_CANDIDATES_PER_CYCLE = 10

# A summary shorter than this gives the writer nothing concrete to work with, which
# is where hallucinated detail comes from.
MIN_SUMMARY_CHARS = 60

# Best credibility a source can realistically be scored at. Derived from observed
# editorial scoring, not invented: arXiv preprints scored 9, GitHub repos 6-7,
# Ask HN threads 4-6, general web results 5-6.
SOURCE_CREDIBILITY_CEILING = {
    "arxiv": 9.0,
    "github": 7.0,
    "hn": 7.0,
    "web": 6.0,
}

# Self-posts asking the community a question are discussion, not a contribution.
LOW_VALUE_TITLE_PATTERNS = (
    re.compile(r"^\s*ask hn\b", re.I),
    re.compile(r"^\s*tell hn\b", re.I),
    re.compile(r"\bendorsement\b", re.I),
)


def _parse_published(value: Optional[str]) -> Optional[datetime]:
    """Parse the assorted timestamp formats the discovery sources return."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _credibility_ceiling(candidate: TopicCandidate) -> float:
    ceiling = SOURCE_CREDIBILITY_CEILING.get(candidate.source, 6.0)
    # An arXiv link posted to HN is still an arXiv paper.
    if candidate.source == "hn" and "arxiv.org" in (candidate.url or ""):
        ceiling = max(ceiling, SOURCE_CREDIBILITY_CEILING["arxiv"])
    if any(p.search(candidate.title or "") for p in LOW_VALUE_TITLE_PATTERNS):
        ceiling = min(ceiling, 5.0)
    return ceiling


def _rank_score(candidate: TopicCandidate, now: datetime) -> float:
    """Higher is more promising. Credibility dominates; recency breaks ties."""
    published = _parse_published(candidate.published_at)
    if published is None:
        recency = 0.0
    else:
        age_days = max(0.0, (now - published).total_seconds() / 86400.0)
        recency = max(0.0, 1.0 - age_days / MAX_CANDIDATE_AGE_DAYS)
    return _credibility_ceiling(candidate) + 2.0 * recency


def prefilter_candidates(
    candidates: List[TopicCandidate],
    persona: PersonaConfig,
    limit: int = MAX_CANDIDATES_PER_CYCLE,
) -> List[TopicCandidate]:
    """
    Drop candidates that cannot clear the persona's thresholds, then return the most
    promising `limit` survivors.
    """
    now = datetime.now(timezone.utc)
    min_credibility = persona.editorial_thresholds.min_credibility
    survivors: List[TopicCandidate] = []
    dropped: dict = {"stale": 0, "thin": 0, "low_credibility": 0}

    for cand in candidates:
        published = _parse_published(cand.published_at)
        if published is not None and (now - published) > timedelta(days=MAX_CANDIDATE_AGE_DAYS):
            dropped["stale"] += 1
            continue

        if len((cand.summary or "").strip()) < MIN_SUMMARY_CHARS:
            dropped["thin"] += 1
            continue

        if _credibility_ceiling(cand) < min_credibility:
            dropped["low_credibility"] += 1
            continue

        survivors.append(cand)

    survivors.sort(key=lambda c: _rank_score(c, now), reverse=True)
    selected = survivors[:limit]

    logger.info(
        "Pre-filter: %d candidates -> %d evaluated "
        "(dropped %d stale, %d thin, %d below credibility %.1f; %d over the per-cycle cap)",
        len(candidates), len(selected), dropped["stale"], dropped["thin"],
        dropped["low_credibility"], min_credibility, max(0, len(survivors) - len(selected)),
    )
    return selected
