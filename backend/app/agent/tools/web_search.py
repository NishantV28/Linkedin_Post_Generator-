import os
import logging
import hashlib
import httpx
from typing import List
from datetime import datetime, timezone
from backend.app.agent.persona.schema import PersonaConfig
from backend.app.agent.tools.schema import TopicCandidate
from backend.app.core.config import settings

logger = logging.getLogger("autonomous_agent.tools.web")

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

def fetch_web_candidates(persona: PersonaConfig, limit: int = 3) -> List[TopicCandidate]:
    """
    Fetch live web news/articles matching persona's stable interests.
    Uses Tavily API if TAVILY_API_KEY is available; otherwise gracefully falls back to DuckDuckGo search.
    """
    candidates: List[TopicCandidate] = []
    api_key = settings.TAVILY_API_KEY or os.getenv("TAVILY_API_KEY")

    query_keywords = [k for k in persona.stable_interests if not k.startswith("cs.")]
    query = f"latest {query_keywords[0] if query_keywords else persona.domain} research breakthrough"

    if api_key:
        try:
            headers = {"Content-Type": "application/json"}
            payload = {
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": limit
            }
            with httpx.Client(timeout=10.0, headers=headers) as client:
                res = client.post(TAVILY_SEARCH_URL, json=payload)
                if res.status_code == 200:
                    results = res.json().get("results", [])
                    for r in results:
                        title = r.get("title", "").strip()
                        url = r.get("url", "")
                        content = r.get("content", "")
                        if title and url:
                            cand_id = f"web_{hashlib.md5(url.encode()).hexdigest()[:12]}"
                            candidates.append(
                                TopicCandidate(
                                    id=cand_id,
                                    title=title,
                                    summary=content[:400],
                                    url=url,
                                    source="web",
                                    published_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                                )
                            )
                    return candidates
        except Exception as e:
            logger.warning(f"Tavily API search failed: {e}. Falling back to DuckDuckGo.")

    # Fallback to DuckDuckGo search (no API key needed)
    try:
        ddg_url = "https://html.duckduckgo.com/html/"
        data = {"q": query}
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        with httpx.Client(timeout=10.0, headers=headers) as client:
            res = client.post(ddg_url, data=data)
            if res.status_code == 200:
                # Basic parsing of search result links
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(res.text, "html.parser")
                results = soup.find_all("a", class_="result__url", limit=limit)
                titles = soup.find_all("a", class_="result__a", limit=limit)
                snippets = soup.find_all("a", class_="result__snippet", limit=limit)

                for i in range(min(len(titles), limit)):
                    t = titles[i].get_text(strip=True)
                    u = results[i]["href"] if i < len(results) and "href" in results[i].attrs else "https://duckduckgo.com"
                    s = snippets[i].get_text(strip=True) if i < len(snippets) else t

                    cand_id = f"web_{hashlib.md5(u.encode()).hexdigest()[:12]}"
                    candidates.append(
                        TopicCandidate(
                            id=cand_id,
                            title=t,
                            summary=s[:400],
                            url=u,
                            source="web",
                            published_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                        )
                    )
    except Exception as e:
        logger.error(f"DuckDuckGo fallback web search error: {e}")

    return candidates
