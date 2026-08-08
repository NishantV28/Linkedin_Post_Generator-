import logging
from typing import List
from backend.app.agent.persona.schema import PersonaConfig
from backend.app.agent.tools.schema import TopicCandidate
from backend.app.agent.tools.hn import fetch_hn_candidates
from backend.app.agent.tools.arxiv import fetch_arxiv_candidates
from backend.app.agent.tools.github_trending import fetch_github_candidates
from backend.app.agent.tools.web_search import fetch_web_candidates

logger = logging.getLogger("autonomous_agent.tools.discovery")

def discover_all_candidates(persona: PersonaConfig) -> List[TopicCandidate]:
    """
    Aggregate topic candidates across Hacker News, arXiv, GitHub, and Web search.
    Each source is executed inside a try/except block so one failing API does not halt discovery.
    """
    all_candidates: List[TopicCandidate] = []
    seen_urls = set()

    sources = [
        ("HackerNews", fetch_hn_candidates),
        ("arXiv", fetch_arxiv_candidates),
        ("GitHub", fetch_github_candidates),
        ("WebSearch", fetch_web_candidates)
    ]

    for source_name, fetch_fn in sources:
        try:
            logger.info(f"Fetching candidates from {source_name} for persona '{persona.name}'...")
            cands = fetch_fn(persona)
            added_count = 0
            for c in cands:
                if c.url not in seen_urls:
                    seen_urls.add(c.url)
                    all_candidates.append(c)
                    added_count += 1
            logger.info(f"{source_name} yielded {added_count} unique candidates.")
        except Exception as e:
            logger.error(f"Error fetching from {source_name}: {e}. Continuing with remaining sources.")

    logger.info(f"Total aggregated raw candidates: {len(all_candidates)}")
    return all_candidates
