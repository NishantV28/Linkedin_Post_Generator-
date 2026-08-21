"""
Discovery from feeds named by the persona.

The other sources are fixed places that happen to suit an AI-research persona. This
one is whatever the persona says it reads, which is what lets the same machinery
serve a persona in a field with no arXiv equivalent - a design newsletter, a company
engineering blog, a subreddit's feed.

Parsed with the standard library rather than a feed package: RSS and Atom differ in
tag names but both are plain XML, and the fields needed here are few enough that
another dependency would not pay for itself.
"""

import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from backend.app.agent.persona.schema import PersonaConfig
from backend.app.agent.tools.schema import TopicCandidate

logger = logging.getLogger("autonomous_agent.tools.rss")

FEED_TIMEOUT_SECONDS = 20.0
MAX_PER_FEED = 8

# Atom uses <entry>/<summary>, RSS uses <item>/<description>. Handling both is a
# handful of lookups, and a persona should not have to care which one its source
# publishes.
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _text(element: Optional[ET.Element]) -> str:
    return (element.text or "").strip() if element is not None else ""


def _parse_date(raw: str) -> str:
    """
    Normalise a feed's date to ISO 8601, falling back to now.

    Feeds are inconsistent here - RFC 822, ISO, and various near-misses all appear -
    and the prefilter only needs an approximate age, so an unparseable date is better
    treated as recent than used to discard an otherwise good candidate.
    """
    raw = (raw or "").strip()
    if not raw:
        return datetime.now(timezone.utc).isoformat()

    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
    ):
        try:
            parsed = datetime.strptime(raw, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        except ValueError:
            continue

    logger.debug(f"Unrecognised feed date '{raw}'; treating as current.")
    return datetime.now(timezone.utc).isoformat()


def _entries(root: ET.Element) -> List[ET.Element]:
    """Items from either an RSS or an Atom document."""
    items = root.findall(".//item")
    if items:
        return items
    return root.findall(".//atom:entry", _ATOM_NS)


def _entry_fields(entry: ET.Element) -> tuple:
    """(title, url, summary, published) from an RSS item or Atom entry."""
    title = _text(entry.find("title")) or _text(entry.find("atom:title", _ATOM_NS))

    url = _text(entry.find("link"))
    if not url:
        link_el = entry.find("atom:link", _ATOM_NS)
        if link_el is not None:
            url = (link_el.get("href") or "").strip()

    summary = (
        _text(entry.find("description"))
        or _text(entry.find("atom:summary", _ATOM_NS))
        or _text(entry.find("atom:content", _ATOM_NS))
    )

    published = (
        _text(entry.find("pubDate"))
        or _text(entry.find("atom:published", _ATOM_NS))
        or _text(entry.find("atom:updated", _ATOM_NS))
    )

    return title, url, summary, published


def fetch_rss_candidates(persona: PersonaConfig, max_results: int = 15) -> List[TopicCandidate]:
    """Candidates from every feed this persona lists."""
    sources_cfg = getattr(persona, "discovery_sources", None)
    feeds = list(getattr(sources_cfg, "rss_feeds", []) or [])
    if not feeds:
        return []

    candidates: List[TopicCandidate] = []

    for feed_url in feeds:
        # One unreachable or malformed feed should cost that feed, not the others and
        # not the cycle.
        try:
            with httpx.Client(timeout=FEED_TIMEOUT_SECONDS, follow_redirects=True) as client:
                response = client.get(feed_url, headers={"User-Agent": "autonomous-agent/1.0"})
            if response.status_code != 200:
                logger.warning(f"Feed {feed_url} returned {response.status_code}; skipping.")
                continue

            root = ET.fromstring(response.content)
        except Exception as err:
            logger.warning(f"Could not read feed {feed_url}: {err}")
            continue

        added = 0
        for entry in _entries(root):
            if added >= MAX_PER_FEED or len(candidates) >= max_results:
                break

            title, url, summary, published = _entry_fields(entry)
            if not title or not url:
                continue

            candidates.append(TopicCandidate(
                id=hashlib.sha256(url.encode()).hexdigest()[:16],
                title=title,
                summary=summary[:1000],
                url=url,
                source="rss",
                published_at=_parse_date(published),
            ))
            added += 1

        logger.info(f"Feed {feed_url} yielded {added} candidates.")

    return candidates
