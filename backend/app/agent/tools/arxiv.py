import logging
import hashlib
import xml.etree.ElementTree as ET
import httpx
from typing import List
from datetime import datetime, timezone
from backend.app.agent.persona.schema import PersonaConfig
from backend.app.agent.tools.schema import TopicCandidate

logger = logging.getLogger("autonomous_agent.tools.arxiv")

ARXIV_API_URL = "http://export.arxiv.org/api/query"

# Namespace mappings for arXiv Atom XML feed
NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom"
}

def fetch_arxiv_candidates(persona: PersonaConfig, max_results: int = 5) -> List[TopicCandidate]:
    """
    Fetch recent arXiv research papers matching persona's category or interest keywords.
    Uses public arXiv Atom API (100% public, no API key needed).
    """
    candidates: List[TopicCandidate] = []

    # Infer relevant categories based on persona domain / interests
    search_queries = []
    for interest in persona.stable_interests:
        if interest.startswith("cs."):
            search_queries.append(f"cat:{interest}")
        else:
            search_queries.append(f"all:{interest}")

    if not search_queries:
        search_queries = ["cat:cs.AI", "cat:cs.LG", "cat:cs.CL"]

    query_str = " OR ".join(search_queries[:4])

    headers = {
        "User-Agent": "AutonomousPersonaAgent/1.0"
    }

    try:
        params = {
            "search_query": query_str,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": max_results
        }

        with httpx.Client(timeout=15.0, headers=headers) as client:
            res = client.get(ARXIV_API_URL, params=params)
            if res.status_code != 200:
                logger.warning(f"arXiv API returned status code {res.status_code}")
                return candidates

            root = ET.fromstring(res.text)
            entries = root.findall("atom:entry", NAMESPACES)

            for entry in entries:
                id_elem = entry.find("atom:id", NAMESPACES)
                title_elem = entry.find("atom:title", NAMESPACES)
                summary_elem = entry.find("atom:summary", NAMESPACES)
                published_elem = entry.find("atom:published", NAMESPACES)

                if title_elem is None or summary_elem is None:
                    continue

                raw_title = " ".join(title_elem.text.split())
                raw_summary = " ".join(summary_elem.text.split())
                url = id_elem.text.strip() if id_elem is not None else ""

                cand_id = f"arxiv_{hashlib.md5(url.encode()).hexdigest()[:12]}"
                pub_time = published_elem.text.strip() if published_elem is not None else datetime.now(timezone.utc).isoformat()

                candidates.append(
                    TopicCandidate(
                        id=cand_id,
                        title=raw_title,
                        summary=raw_summary[:500],  # Keep abstract concise for candidate evaluation
                        url=url,
                        source="arxiv",
                        published_at=pub_time
                    )
                )

    except Exception as e:
        logger.error(f"Error fetching arXiv candidates: {e}")

    return candidates
