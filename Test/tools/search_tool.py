# tools/search_tool.py
# ---------------------------------------------------------------------------
# DuckDuckGo news search tool with per-region caching.
# NewsAPI-first provider search with DuckDuckGo fallback.
#
# URL PRESERVATION: Returns pre-formatted markdown links that agents MUST copy
# exactly to prevent URL hallucination.
#
# JSON INPUT VALIDATION: Handles malformed JSON from LLM tool calls by normalizing
# input formats like [{"query": "...", "max_results": 5}, ["result"]] to valid dicts.
# ---------------------------------------------------------------------------

import os
import json as _json
import re
from datetime import datetime
from typing import Dict, Type, Optional, List, Any, Union

from langchain_community.tools import DuckDuckGoSearchResults
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from pydantic import BaseModel, Field, ValidationError

# Import crewai tools with graceful fallback
try:
    from crewai.tools import tool, BaseTool
except ImportError:
    # Provide dummy decorators/classes when crewai is not available
    def tool(func=None, *args, **kwargs):
        """Dummy decorator when crewai is not installed."""
        if func is not None:
            return func
        return lambda f: f
    
    class BaseTool:
        """Dummy BaseTool when crewai is not installed."""
        pass

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

    countries = fetch_country_data()
    info = countries.get(country_code.upper(), {})
    region_code = info.get("ddg_region", _DEFAULT_DDG_REGION)

    if region_code not in _DDG_WRAPPERS_CACHE:
        wrapper = DuckDuckGoSearchAPIWrapper(
            max_results=5, time="y", region=region_code
        )
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


def _format_search_result(
    headline: str, url: str, snippet: str, source: str = "", date: str = ""
) -> str:
    """
    Format a single search result with URL preservation.

    The MARKDOWN_LINK line is pre-formatted so agents can copy it EXACTLY.
    This prevents URL hallucination - agents should NEVER create URLs themselves.
    """
    lines = []

    # Section header for easy parsing
    lines.append("=== SEARCH_RESULT ===")

    # Core data
    lines.append(f"HEADLINE: {headline}")

    if source:
        lines.append(f"SOURCE: {source}")
    if date:
        lines.append(f"DATE: {date}")

    # Snippet (truncated)
    safe_snippet = snippet[:250].strip() if snippet else ""
    if safe_snippet:
        lines.append(f"SNIPPET: {safe_snippet}")

    # URL (exact, for reference)
    if url:
        lines.append(f"URL: {url}")

    # PRE-FORMATTED MARKDOWN LINK - COPY THIS EXACTLY
    # This is the key line that prevents URL hallucination
    if url and headline:
        lines.append(f"MARKDOWN_LINK: [{headline}]({url})")
    elif headline:
        lines.append(f"MARKDOWN_LINK: **{headline}** (no URL available)")

    lines.append("=== END_RESULT ===")

    return "\n".join(lines)


@tool("DuckDuckGo News Search")
def search_news(query: str) -> str:
    """Search for recent news articles using DuckDuckGo. Returns structured results with
    pre-formatted markdown links that MUST be copied exactly.

    IMPORTANT: This tool returns MARKDOWN_LINK lines that you should copy VERBATIM.
    Do NOT create, modify, or guess URLs - only copy from MARKDOWN_LINK lines.

    Use this as a FALLBACK when NewsAPI Provider Search returns no results."""
    try:
        ddg = _get_ddg_tool()
        results = ddg.invoke(query)
        if isinstance(results, list):
            LOW_QUALITY_DOMAINS = {"wikipedia.org", "en.wikipedia.org"}
            preferred, fallback = [], []
            seen_domains: set = set()

            for r in results[:5]:
                headline = r.get("title", "").strip()
                snippet = r.get("snippet", r.get("body", "")).strip()
                url = r.get("link", r.get("url", "")).strip()

                if not (headline or snippet):
                    continue

                try:
                    from urllib.parse import urlparse

                    domain = urlparse(url).netloc.lstrip("www.")
                    source = domain
                except Exception:
                    domain = url
                    source = ""

                # Format with URL preservation
                entry = _format_search_result(
                    headline=headline, url=url, snippet=snippet, source=source, date=""
                )

                if domain in LOW_QUALITY_DOMAINS:
                    fallback.append(entry)
                elif domain not in seen_domains:
                    seen_domains.add(domain)
                    preferred.append(entry)

            combined = preferred[:3] if preferred else fallback[:2]

            if combined:
                header = (
                    "SEARCH_RESULTS_START\n"
                    "INSTRUCTIONS: Copy MARKDOWN_LINK lines EXACTLY. Never modify URLs.\n"
                    "---"
                )
                return (
                    header
                    + "\n"
                    + "\n---\n".join(combined)
                    + "\n---\nSEARCH_RESULTS_END"
                )
            return "No results found."
        return str(results)[:1500]
    except Exception as e:
        return f"Search failed: {str(e)}"


# ---------------------------------------------------------------------------
# NewsAPI Provider Search — tries NewsAPI FIRST, falls back to DuckDuckGo
# ---------------------------------------------------------------------------

_NEWSAPI_BASE_URL = "https://newsapi.org/v2/everything"


class ProviderNewsAPIInput(BaseModel):
    query: str = Field(
        ...,
        description="Search query for financial provider news. "
        "Examples: 'HDFC Bank FD rates 2026', 'best fixed deposit rates India SBI 2026'",
    )
    max_results: int = Field(
        default=5, description="Maximum number of articles to return (1-10, default 5)."
    )


def _normalize_tool_input(input_data: Any) -> Dict[str, Any]:
    """
    Normalize malformed LLM tool call inputs to valid dict format.
    
    Handles common malformed patterns:
    - [{"query": "...", "max_results": 5}, ["result"]] -> {"query": "...", "max_results": 5}
    - [{"query": "..."}] -> {"query": "..."}
    - {"query": "..."} -> {"query": "..."} (already valid)
    
    Args:
        input_data: Raw input from LLM tool call (may be malformed)
        
    Returns:
        Normalized dict with 'query' and optionally 'max_results'
        
    Raises:
        ValueError: If input cannot be normalized to valid format
    """
    # Case 1: Already a valid dict
    if isinstance(input_data, dict):
        if "query" in input_data:
            return {
                "query": str(input_data["query"]),
                "max_results": int(input_data.get("max_results", 5))
            }
        raise ValueError(f"Invalid input: dict missing 'query' key: {input_data}")
    
    # Case 2: List with dict as first element (malformed pattern)
    if isinstance(input_data, list) and len(input_data) > 0:
        first_item = input_data[0]
        if isinstance(first_item, dict) and "query" in first_item:
            return {
                "query": str(first_item["query"]),
                "max_results": int(first_item.get("max_results", 5))
            }
        raise ValueError(f"Invalid input: list first element is not a valid dict: {input_data}")
    
    # Case 3: String that looks like JSON
    if isinstance(input_data, str):
        # Try to parse as JSON
        try:
            parsed = _json.loads(input_data)
            return _normalize_tool_input(parsed)
        except _json.JSONDecodeError:
            pass
        
        # Try to extract JSON-like pattern from string
        # Pattern: [{"query": "...", "max_results": N}] or {"query": "...", "max_results": N}
        json_pattern = r'\[?\s*\{\s*"query"\s*:\s*"([^"]+)"\s*(?:,\s*"max_results"\s*:\s*(\d+))?\s*\}\s*\]?'
        match = re.search(json_pattern, input_data)
        if match:
            query = match.group(1)
            max_results = int(match.group(2)) if match.group(2) else 5
            return {"query": query, "max_results": max_results}
        
        # If it's just a plain string, treat it as the query
        if input_data.strip():
            return {"query": input_data.strip(), "max_results": 5}
        
        raise ValueError(f"Invalid input: empty or unparseable string: {input_data}")
    
    raise ValueError(f"Invalid input type: {type(input_data).__name__}, value: {input_data}")


class ProviderNewsAPISearchTool(BaseTool):
    """
    Search NewsAPI.org for financial provider news first.
    If NewsAPI returns no results (or is unavailable), automatically falls back
    to DuckDuckGo News Search.

    This is the PREFERRED search tool for analysis and research pipelines.
    It provides structured, high-quality results from NewsAPI, with DuckDuckGo
    as a reliable fallback.

    URL PRESERVATION: Returns pre-formatted MARKDOWN_LINK lines that agents
    MUST copy exactly. Never create or modify URLs - only copy from results.
    """

    name: str = "NewsAPI Provider Search"
    description: str = (
        "Searches NewsAPI.org for current news about financial providers, banks, "
        "and investment products. Returns structured article results with PRE-FORMATTED "
        "markdown links that you MUST copy exactly. "
        "If NewsAPI returns no results or is unavailable, automatically falls back "
        "to DuckDuckGo News Search. "
        "Use this as your PRIMARY search tool for finding provider rates, news, "
        "and financial data. It is faster and more structured than DuckDuckGo alone. "
        "Input: query (required), max_results (optional, default 5). "
        "Requires NEWS_API_KEY env var for NewsAPI; fallback works without it."
    )
    args_schema: Type[BaseModel] = ProviderNewsAPIInput

    def _run(self, query: str, max_results: int = 5) -> str:
        """
        Execute the search with input validation.
    
        Args:
            query: Search query for financial provider news.
            max_results: Maximum number of results (1-10, default 5).
    
        Returns:
            Formatted search results as markdown
    
        Raises:
            ValueError: If input is invalid
        """
        # Validate query
        query = str(query).strip()
        if not query:
            raise ValueError("Query cannot be empty")

        # Validate max_results
        try:
            max_results = int(max_results)
            max_results = min(max(1, max_results), 10)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid max_results: {max_results!r}. Error: {e}")
        
        current_year = datetime.now().year

        # ── Attempt 1: NewsAPI ──
        newsapi_result = self._search_newsapi(query, max_results, current_year)
        if newsapi_result and "NO_RESULTS" not in newsapi_result:
            header = (
                "SEARCH_RESULTS_START\n"
                "SOURCE: NewsAPI\n"
                "INSTRUCTIONS: Copy MARKDOWN_LINK lines EXACTLY into your output. "
                "Never create, modify, or guess URLs - only copy from MARKDOWN_LINK lines below.\n"
                "---"
            )
            return header + "\n" + newsapi_result + "\n---\nSEARCH_RESULTS_END"

        # ── Attempt 2: DuckDuckGo fallback ──
        ddg_result = self._search_ddg(query)
        if (
            ddg_result
            and "No results found" not in ddg_result
            and "Search failed" not in ddg_result
        ):
            return ddg_result  # Already has proper formatting

        # Both failed
        return (
            f"No results found from either NewsAPI or DuckDuckGo for: '{query}'. "
            f"Try broadening the query or removing the year."
        )

    def _search_newsapi(
        self, query: str, max_results: int, current_year: int
    ) -> Optional[str]:
        """Search NewsAPI.org and return formatted results with URL preservation."""
        api_key = os.getenv("NEWS_API_KEY")
        if not api_key:
            return None

        try:
            import requests

            # Build the query — ensure current year is included
            if str(current_year) not in query:
                search_query = f"{query} {current_year}"
            else:
                search_query = query

            # Sort by relevancy for rate/provider searches
            params = {
                "q": search_query,
                "apiKey": api_key,
                "language": "en",
                "sortBy": "relevancy",
                "pageSize": max_results,
            }

            resp = requests.get(_NEWSAPI_BASE_URL, params=params, timeout=15)
            if resp.status_code == 429:
                return None  # Rate limited — fall back to DDG
            if resp.status_code != 200:
                return None

            data = resp.json()
            articles = data.get("articles", [])

            if not articles:
                # Try without year constraint (broader search)
                if str(current_year) in search_query:
                    broader_query = query.replace(str(current_year), "").strip()
                    params["q"] = broader_query
                    resp2 = requests.get(_NEWSAPI_BASE_URL, params=params, timeout=15)
                    if resp2.status_code == 200:
                        data2 = resp2.json()
                        articles = data2.get("articles", [])

            if not articles:
                return "NO_RESULTS"

            # Format results with URL preservation
            formatted_results = []
            seen_titles = set()

            for art in articles[:max_results]:
                headline = (art.get("title") or "").strip()
                if not headline or headline == "[Removed]":
                    continue

                # Dedup by title
                title_key = headline.lower().strip()[:60]
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)

                source = (art.get("source", {}).get("name") or "Unknown").strip()
                pub_date = (art.get("publishedAt") or "")[:10]
                url = (art.get("url") or "").strip()
                desc = (art.get("description") or "")[:250].strip()

                # Truncate description to ~2 sentences
                if desc and len(desc) > 200:
                    for sep in [". ", "! ", "? "]:
                        idx = desc[:200].rfind(sep)
                        if idx > 50:
                            desc = desc[: idx + 1]
                            break
                    else:
                        desc = desc[:200] + "..."

                # Use the standardized formatter with URL preservation
                entry = _format_search_result(
                    headline=headline,
                    url=url,
                    snippet=desc,
                    source=source,
                    date=pub_date,
                )
                formatted_results.append(entry)

            return (
                "\n---\n".join(formatted_results) if formatted_results else "NO_RESULTS"
            )

        except Exception:
            return None

    def _search_ddg(self, query: str) -> Optional[str]:
        """Fall back to DuckDuckGo search."""
        try:
            return search_news.run(query)
        except Exception:
            return None


# Singleton instance
provider_news_api_tool = ProviderNewsAPISearchTool()


# ---------------------------------------------------------------------------
# URL Registry for cross-agent URL preservation
# ---------------------------------------------------------------------------


class URLRegistry:
    """
    Global registry to store real URLs from search tools.
    Prevents URL hallucination by providing exact URL lookup.

    Usage:
    1. Search tools register URLs automatically
    2. Post-processing resolves any URL markers in final reports
    3. Validation removes any URLs not from registry (hallucinated)
    """

    _registry: Dict[str, dict] = {}

    @classmethod
    def register(cls, headline: str, url: str, source: str = "") -> str:
        """Register a URL and return a reference key"""
        if not url or not headline:
            return ""

        import hashlib

        key = hashlib.md5(headline.lower().encode()).hexdigest()[:8]

        cls._registry[key] = {"headline": headline, "url": url, "source": source}

        return key

    @classmethod
    def get_all_urls(cls) -> Dict[str, dict]:
        """Get all registered URLs"""
        return cls._registry.copy()

    @classmethod
    def clear(cls):
        """Clear registry (call at start of new session)"""
        cls._registry = {}

    @classmethod
    def is_registered(cls, url: str) -> bool:
        """Check if a URL is in the registry"""
        return any(entry["url"] == url for entry in cls._registry.values())

    @classmethod
    def validate_report(cls, markdown_report: str) -> str:
        """
        Validate URLs in a markdown report.
        Replace hallucinated URLs (not in registry) with plain text.
        """
        import re

        def check_url(match):
            text = match.group(1)
            url = match.group(2)

            if cls.is_registered(url):
                return f"[{text}]({url})"
            else:
                # URL not in registry - likely hallucinated
                # Remove the link but keep the text
                return f"**{text}**"

        # Find all markdown links and validate
        pattern = r"\[([^\]]+)\]\(([^)]+)\)"
        return re.sub(pattern, check_url, markdown_report)
