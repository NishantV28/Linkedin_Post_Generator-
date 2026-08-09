import logging
import hashlib
import html
import re
import httpx
from typing import List
from datetime import datetime, timedelta, timezone
from backend.app.agent.persona.schema import PersonaConfig
from backend.app.agent.tools.schema import TopicCandidate

logger = logging.getLogger("autonomous_agent.tools.hn")

HN_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"

# Only consider stories from the last few weeks as "discovery".
RECENCY_WINDOW_DAYS = 21

# Engagement floor. Below this a story is a link nobody engaged with, which gives the
# writer nothing to react to.
MIN_POINTS = 20
MIN_COMMENTS = 5

# Comments pulled per story for context. Enough to show what the argument is about
# without turning the candidate summary into a transcript.
TOP_COMMENTS = 3
MAX_COMMENT_CHARS = 220

HN_ITEM_URL = "https://hn.algolia.com/api/v1/items/{object_id}"

HN_TIMEOUT_SECONDS = 20.0


def _fetch_top_comments(client: httpx.Client, object_id) -> str:
    """
    Pull the leading comments on a story.

    A headline alone tells the writer nothing about why a story matters; the argument
    in the comments is the part worth reacting to. Failures are swallowed - this is
    enrichment, and a story without comment context is still a usable candidate.
    """
    if not object_id:
        return ""
    try:
        res = client.get(HN_ITEM_URL.format(object_id=object_id), timeout=HN_TIMEOUT_SECONDS)
        if res.status_code != 200:
            return ""
        children = res.json().get("children") or []
        snippets = []
        for child in children:
            text = child.get("text") or ""
            text = re.sub(r"<[^>]+>", " ", text)          # strip HTML markup
            text = html.unescape(" ".join(text.split()))
            if len(text) < 60:                             # skip one-liners
                continue
            snippets.append(text[:MAX_COMMENT_CHARS])
            if len(snippets) >= TOP_COMMENTS:
                break
        return " | ".join(snippets)
    except Exception as err:
        logger.debug(f"Could not fetch HN comments for {object_id}: {err}")
        return ""

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

    with httpx.Client(timeout=HN_TIMEOUT_SECONDS, headers=headers) as client:
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
                    # Engagement floor: a story nobody discussed is not a story people
                    # are arguing about, and discussion is what makes a source worth
                    # reacting to rather than summarising.
                    "numericFilters": (
                        f"created_at_i>{cutoff},"
                        f"points>{MIN_POINTS},"
                        f"num_comments>{MIN_COMMENTS}"
                    )
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

                    points = hit.get("points", 0)
                    num_comments = hit.get("num_comments", 0)
                    story_text = " ".join((hit.get("story_text") or "").split())

                    # The old summary was just the title plus two counts, which gave the
                    # judge and writer nothing but a headline to reason about - the main
                    # route by which invented detail got into posts.
                    summary_parts = [
                        f"Hacker News discussion with {points} points and {num_comments} comments."
                    ]
                    if story_text:
                        summary_parts.append(f"Submitter's text: {story_text[:400]}")
                    comment_text = _fetch_top_comments(client, hit.get("objectID"))
                    if comment_text:
                        summary_parts.append(f"What commenters are saying: {comment_text}")
                    summary = " ".join(summary_parts)

                    cand_id = f"hn_{hashlib.md5(url.encode()).hexdigest()[:12]}"

                    candidates.append(
                        TopicCandidate(
                            id=cand_id,
                            title=title,
                            summary=summary,
                            url=url,
                            source="hn",
                            published_at=pub_time,
                            engagement=points
                        )
                    )
            except Exception as e:
                logger.error(f"Error fetching HN candidates for keyword '{keyword}': {e}")
                continue

    return candidates
