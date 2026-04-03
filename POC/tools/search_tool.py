# tools/search_tool.py
# ---------------------------------------------------------------------------
# DuckDuckGo news search tool with per-region caching.
# ---------------------------------------------------------------------------

from typing import Dict
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from crewai.tools import tool

from tools.config import fetch_country_data, _DEFAULT_DDG_REGION

# ---------------------------------------------------------------------------
# DuckDuckGo wrapper cache — one wrapper per region, created on demand
# ---------------------------------------------------------------------------
_DDG_WRAPPERS_CACHE: Dict[str, DuckDuckGoSearchResults] = {}
_CURRENT_DDG_REGION = _DEFAULT_DDG_REGION

ddg_news_wrapper = DuckDuckGoSearchAPIWrapper(
    max_results=5, time="y", region=_DEFAULT_DDG_REGION
)
langchain_ddg_tool = DuckDuckGoSearchResults(
    api_wrapper=ddg_news_wrapper, output_format="list"
)


def set_search_region(country_code: str) -> str:
    """
    Get or create a cached DuckDuckGo wrapper for the user's region.
    Returns the DDG region code applied.
    """
    global _CURRENT_DDG_REGION

    countries   = fetch_country_data()
    info        = countries.get(country_code.upper(), {})
    region_code = info.get("ddg_region", _DEFAULT_DDG_REGION)

    if region_code not in _DDG_WRAPPERS_CACHE:
        wrapper = DuckDuckGoSearchAPIWrapper(max_results=5, time="y", region=region_code)
        _DDG_WRAPPERS_CACHE[region_code] = DuckDuckGoSearchResults(
            api_wrapper=wrapper, output_format="list"
        )

    _CURRENT_DDG_REGION = region_code
    return region_code


def _get_ddg_tool() -> DuckDuckGoSearchResults:
    """Return the DuckDuckGo tool for the active region."""
    return _DDG_WRAPPERS_CACHE.get(
        _CURRENT_DDG_REGION,
        DuckDuckGoSearchResults(
            api_wrapper=DuckDuckGoSearchAPIWrapper(
                max_results=5, time="y", region=_DEFAULT_DDG_REGION
            ),
            output_format="list",
        ),
    )


@tool("DuckDuckGo News Search")
def search_news(query: str) -> str:
    """Search for recent news articles using DuckDuckGo. Returns compressed title, snippet,
    and URL. Prioritizes authoritative non-Wikipedia sources. Results are cached to avoid
    redundant searches."""
    try:
        ddg = _get_ddg_tool()
        results = ddg.invoke(query)
        if isinstance(results, list):
            LOW_QUALITY_DOMAINS = {"wikipedia.org", "en.wikipedia.org"}
            preferred, fallback = [], []
            seen_domains: set = set()

            for r in results[:5]:
                title   = r.get("title", "").strip()
                snippet = r.get("snippet", r.get("body", "")).strip()[:250]
                url     = r.get("link",    r.get("url", "")).strip()
                if not (title or snippet):
                    continue
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc.lstrip("www.")
                except Exception:
                    domain = url

                entry = f"Title: {title}\nSnippet: {snippet}\nURL: {url}"
                if domain in LOW_QUALITY_DOMAINS:
                    fallback.append(entry)
                elif domain not in seen_domains:
                    seen_domains.add(domain)
                    preferred.append(entry)

            combined = preferred[:3] if preferred else fallback[:2]
            return "\n---\n".join(combined) if combined else "No results found."
        return str(results)[:1500]
    except Exception as e:
        return f"Search failed: {str(e)}"
