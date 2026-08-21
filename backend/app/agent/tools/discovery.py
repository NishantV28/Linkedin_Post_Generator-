import logging
from typing import List
from backend.app.agent.persona.schema import PersonaConfig
from backend.app.agent.tools.schema import TopicCandidate
from backend.app.agent.tools.hn import fetch_hn_candidates
from backend.app.agent.tools.arxiv import fetch_arxiv_candidates
from backend.app.agent.tools.github_trending import fetch_github_candidates
from backend.app.agent.tools.web_search import fetch_web_candidates
from backend.app.agent.tools.rss import fetch_rss_candidates

logger = logging.getLogger("autonomous_agent.tools.discovery")

def discover_all_candidates(persona: PersonaConfig) -> List[TopicCandidate]:
    """
    Aggregate topic candidates from the sources this persona reads.

    Which sources those are is part of the persona rather than fixed here: Hacker
    News, arXiv and GitHub suit an AI-research persona and suit almost nothing else,
    which previously confined the whole persona system to one subject area. A persona
    in another field can now be pointed at its own feeds instead.

    Each source runs inside a try/except so one failing API does not halt discovery.
    """
    all_candidates: List[TopicCandidate] = []
    seen_urls = set()

    # Personas created before discovery_sources existed have no such attribute, so
    # they fall back to the original four - the behaviour they were built against.
    enabled = getattr(persona, "discovery_sources", None)

    sources = []
    if enabled is None or enabled.hacker_news:
        sources.append(("HackerNews", fetch_hn_candidates))
    if enabled is None or enabled.arxiv:
        sources.append(("arXiv", fetch_arxiv_candidates))
    if enabled is None or enabled.github:
        sources.append(("GitHub", fetch_github_candidates))
    if enabled is None or enabled.web_search:
        sources.append(("WebSearch", fetch_web_candidates))
    if enabled is not None and enabled.rss_feeds:
        sources.append(("RSS", fetch_rss_candidates))

    if not sources:
        logger.warning(
            f"Persona '{persona.name}' has every discovery source disabled. "
            "No candidates can be found."
        )
        return []

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
