import logging
import hashlib
import httpx
from typing import List
from datetime import datetime, timezone
from backend.app.agent.persona.schema import PersonaConfig
from backend.app.agent.tools.schema import TopicCandidate

logger = logging.getLogger("autonomous_agent.tools.github")

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

def fetch_github_candidates(persona: PersonaConfig, limit: int = 4) -> List[TopicCandidate]:
    """
    Fetch trending or newly updated AI/ML GitHub repositories matching persona domain.
    Uses public GitHub Search API (100% public, no API key needed).
    """
    candidates: List[TopicCandidate] = []

    topic_keywords = [k for k in persona.stable_interests if not k.startswith("cs.")]
    if not topic_keywords:
        topic_keywords = [persona.domain]

    query_term = topic_keywords[0]
    q = f"{query_term} stars:>50 sort:updated-desc"

    headers = {
        "User-Agent": "AutonomousPersonaAgent/1.0",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        params = {
            "q": q,
            "per_page": limit
        }

        with httpx.Client(timeout=20.0, headers=headers) as client:
            res = client.get(GITHUB_SEARCH_URL, params=params)
            if res.status_code != 200:
                logger.warning(f"GitHub API returned status code {res.status_code}")
                return candidates

            data = res.json()
            items = data.get("items", [])

            for item in items:
                name = item.get("full_name", "")
                desc = item.get("description") or "No description provided."
                url = item.get("html_url", "")
                pushed_at = item.get("pushed_at") or datetime.now(timezone.utc).isoformat()
                stars = item.get("stargazers_count", 0)

                title = f"GitHub: {name} ({stars} stars)"
                summary = f"{desc} Language: {item.get('language', 'Python')}. Topics: {', '.join(item.get('topics', []))}"
                cand_id = f"gh_{hashlib.md5(url.encode()).hexdigest()[:12]}"

                candidates.append(
                    TopicCandidate(
                        id=cand_id,
                        title=title,
                        summary=summary,
                        url=url,
                        source="github",
                        published_at=pushed_at
                    )
                )

    except Exception as e:
        logger.error(f"Error fetching GitHub candidates: {e}")

    return candidates
