import logging
import hashlib
import httpx
from typing import List
from datetime import datetime, timedelta, timezone
from backend.app.agent.persona.schema import PersonaConfig
from backend.app.agent.tools.schema import TopicCandidate

logger = logging.getLogger("autonomous_agent.tools.hn")

HN_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"

# Only consider stories from the last few weeks as "discovery".
RECENCY_WINDOW_DAYS = 21

def fetch_hn_candidates(persona: PersonaConfig, limit_per_keyword: int = 3) -> List[TopicCandidate]:
    """
    Fetch relevant Hacker News stories matching persona's stable interests.
    Uses Algolia REST API (100% public, no API key needed).
    """
    candidates: List[TopicCandidate] = []
    seen_urls = set()

    headers = {
        "User-Agent": "AutonomousPersonaAgent/1.0"
    }

    keywords = persona.stable_interests if persona.stable_interests else [persona.domain]

    with httpx.Client(timeout=10.0, headers=headers) as client:
        for keyword in keywords[:5]:  # Query top 5 keywords to prevent rate limiting
            try:
                # Algolia's /search ranks by relevance with no date bound, which
                # returns stories from years ago - live runs surfaced items 2600 and
                # 5700 days old. Restrict to a recent window so "discovery" means
                # current material.
                cutoff = int((datetime.now(timezone.utc) - timedelta(days=RECENCY_WINDOW_DAYS)).timestamp())
                params = {
                    "query": keyword,
                    "tags": "story",
                    "hitsPerPage": limit_per_keyword,
                    "numericFilters": f"created_at_i>{cutoff}"
                }
                res = client.get(HN_ALGOLIA_URL, params=params)
                if res.status_code != 200:
                    logger.warning(f"HN API returned status code {res.status_code} for query '{keyword}'")
                    continue

                data = res.json()
                hits = data.get("hits", [])

                for hit in hits:
                    url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                    title = hit.get("title", "").strip()
                    if not title or url in seen_urls:
                        continue

                    seen_urls.add(url)
                    created_at_i = hit.get("created_at_i")
                    if created_at_i:
                        pub_time = datetime.fromtimestamp(created_at_i, timezone.utc).isoformat().replace("+00:00", "Z")
                    else:
                        pub_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

                    summary = f"{title}. Points: {hit.get('points', 0)}, Comments: {hit.get('num_comments', 0)}"
                    cand_id = f"hn_{hashlib.md5(url.encode()).hexdigest()[:12]}"

                    candidates.append(
                        TopicCandidate(
                            id=cand_id,
                            title=title,
                            summary=summary,
                            url=url,
                            source="hn",
                            published_at=pub_time
                        )
                    )
            except Exception as e:
                logger.error(f"Error fetching HN candidates for keyword '{keyword}': {e}")
                continue

    return candidates
