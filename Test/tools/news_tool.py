# tools/news_tool.py
import os
import time
import random
import requests
from typing import Type, Dict, List, Optional

from crewai.tools import BaseTool, tool
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# GDELT
# ---------------------------------------------------------------------------

GDELT_API_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
_GDELT_LOW_VALUE = {"wikipedia.org", "reddit.com", "quora.com", "answers.yahoo.com"}
_gdelt_last_call_ts: float = 0.0
_GDELT_MIN_INTERVAL: float = 4.0

_GDELT_TIMESPAN_MAP = {
    "1y": "12months", "2y": "12months", "6m": "6months", "3m": "3months",
    "1m": "1months", "12months": "12months", "6months": "6months",
    "3months": "3months", "1months": "1months",
    "30d": "30d", "14d": "14d", "7d": "7d", "12w": "12w", "4w": "4w", "1w": "1w",
}


def _gdelt_wait_for_slot() -> None:
    global _gdelt_last_call_ts
    elapsed = time.monotonic() - _gdelt_last_call_ts
    if elapsed < _GDELT_MIN_INTERVAL:
        time.sleep(_GDELT_MIN_INTERVAL - elapsed + random.uniform(0.1, 0.5))
    _gdelt_last_call_ts = time.monotonic()


def _gdelt_fetch(query: str, max_records: int = 8, timespan: str = "6months") -> str:
    timespan = _GDELT_TIMESPAN_MAP.get(timespan.lower().strip(), timespan)
    retry_waits = [5, 15, 30, 60]

    for attempt in range(4):
        _gdelt_wait_for_slot()
        try:
            resp = requests.get(
                GDELT_API_BASE,
                params={"query": query, "mode": "artlist", "format": "json",
                        "maxrecords": max_records, "timespan": timespan, "sort": "relevance"},
                timeout=20,
            )
            if resp.status_code == 429:
                wait = max(int(resp.headers.get("Retry-After", retry_waits[attempt])),
                           retry_waits[attempt]) + random.uniform(1, 3)
                time.sleep(wait)
                _gdelt_last_call_ts = time.monotonic()
                continue
            resp.raise_for_status()
            articles = resp.json().get("articles", [])
            if not articles:
                return "No GDELT results found."
            lines, seen_domains, seen_titles = [], set(), set()
            for art in articles:
                domain = art.get("domain", "")
                if domain in _GDELT_LOW_VALUE or domain in seen_domains:
                    continue

                # Article-level title dedup (normalised lowercase, first 60 chars)
                title_key = art.get("title", "").lower().strip()[:60]
                if title_key and title_key in seen_titles:
                    continue
                seen_titles.add(title_key)
                seen_domains.add(domain)

                raw_date = art.get("seendate", "")
                date_str = raw_date[:8] if raw_date else "unknown"

                # Tone: GDELT provides comma-separated values; index 0 = overall tone
                # Negative = adverse, Positive = favourable
                tone_label = ""
                tone_raw = art.get("tone", "")
                if tone_raw:
                    try:
                        tone_val = float(str(tone_raw).split(",")[0])
                        if tone_val <= -3.0:
                            tone_label = "⚠ ADVERSE"
                        elif tone_val >= 3.0:
                            tone_label = "✓ POSITIVE"
                        else:
                            tone_label = "~ NEUTRAL"
                    except (ValueError, TypeError):
                        pass

                entry = (
                    f"Title: {art.get('title', '').strip()}\n"
                    f"Date: {date_str}"
                    + (f" | Tone: {tone_label}" if tone_label else "") + "\n"
                    f"URL: {art.get('url', '').strip()}"
                )
                lines.append(entry)
                if len(lines) >= 5:
                    break
            return "\n---\n".join(lines) if lines else "No usable results found."
        except requests.exceptions.RequestException as e:
            if attempt < 3:
                time.sleep(retry_waits[attempt] + random.uniform(1, 3))
                _gdelt_last_call_ts = time.monotonic()
                continue
            return f"GDELT search failed after 4 retries: {e}"
        except Exception as e:
            return f"GDELT search failed: {e}"

    return "GDELT search failed: rate limit persisted."


@tool("GDELT News Search")
def gdelt_news_search(query: str) -> str:
    """Search GDELT's global news index for articles about a topic, entity, or event.
    Best for: AML entity news, corporate investigations, sanctions context.
    Returns title, date, and URL for up to 5 deduplicated articles."""
    return _gdelt_fetch(query, max_records=8, timespan="6months")


class GDELTEntityInput(BaseModel):
    entity_name: str = Field(..., description="Full name of person or organisation.")
    context: str = Field(default="", description="Optional context keywords (e.g. 'sanctions').")
    timespan: str = Field(default="12months", description="Look-back: '3months', '6months', '12months', '30d'.")


class GDELTEntitySearchTool(BaseTool):
    """Structured entity-centric GDELT search for AML / UBO investigations."""

    name: str = "GDELT Entity News Search"
    description: str = (
        "Searches GDELT's global news index for a specific person or organisation. "
        "Use for AML due-diligence and adverse media screening. "
        "Input: entity_name (required), context (optional), timespan (optional). "
        "Returns deduplicated articles with title, date, and URL."
    )
    args_schema: Type[BaseModel] = GDELTEntityInput

    def _run(self, entity_name: str, context: str = "", timespan: str = "12months") -> str:
        query = f'"{entity_name}"'
        if context:
            query += f" {context}"
        return _gdelt_fetch(query, max_records=10, timespan=timespan)


# ---------------------------------------------------------------------------
# ICIJ Offshore Leaks
# ---------------------------------------------------------------------------

ICIJ_RECONCILE_URL = "https://offshoreleaks.icij.org/api/v1/reconcile"
ICIJ_REST_NODE_URL = "https://offshoreleaks.icij.org/api/v1/rest/nodes/{node_id}"
ICIJ_REST_RELS_URL = "https://offshoreleaks.icij.org/api/v1/rest/nodes/{node_id}/relationships"
ICIJ_NODE_PAGE_URL = "https://offshoreleaks.icij.org/nodes/{node_id}"

_ICIJ_DATASETS = ["panama-papers", "pandora-papers", "paradise-papers", "bahamas-leaks", "offshore-leaks"]
_ICIJ_TYPE_MAP = {
    "https://offshoreleaks.icij.org/schema/oldb/entity": "Offshore Entity",
    "https://offshoreleaks.icij.org/schema/oldb/officer": "Officer / Beneficial Owner",
    "https://offshoreleaks.icij.org/schema/oldb/intermediary": "Intermediary / Law Firm",
    "https://offshoreleaks.icij.org/schema/oldb/address": "Registered Address",
    "https://offshoreleaks.icij.org/schema/oldb/other": "Other",
    "https://offshoreleaks.icij.org/schema/oldb/node": "Node",
}
_ICIJ_REL_RISK = {
    "officer_of": "UBO / Director / Shareholder",
    "intermediary_of": "Intermediary (law firm / agent)",
    "registered_address": "Registered Address",
    "same_name_as": "Name alias linkage",
    "same_id_as": "Identifier alias linkage",
    "underlying_of": "Beneficial owner (underlying)",
    "similar_name_and_address": "Possible duplicate — same name+address",
}


def _icij_request(method: str, url: str, payload=None, timeout=15) -> Optional[Dict]:
    headers = {"Accept": "application/json", "User-Agent": "AMLComplianceBot/2.0"}
    for attempt in range(3):
        try:
            if method == "POST":
                headers["Content-Type"] = "application/json"
                resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            else:
                resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code in (429, 503):
                time.sleep(3 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception:
            if attempt == 2:
                return None
            time.sleep(2)
    return None


class ICIJInput(BaseModel):
    name: str = Field(..., description="Full name of the person or company to search.")
    country_code: str = Field(default="", description="Optional ISO-3166-1 alpha-3 country code.")


class ICIJOffshoreLeaksTool(BaseTool):
    """Searches the ICIJ Offshore Leaks Database for AML / UBO screening."""

    name: str = "ICIJ Offshore Leaks Search"
    description: str = (
        "Searches the ICIJ Offshore Leaks Database (Panama Papers, Pandora Papers, Paradise Papers, "
        "Bahamas Leaks, Offshore Leaks) for a person or company. "
        "Returns matched offshore entities, jurisdiction, incorporation status, related officers, "
        "and a direct OffshoreLeaks profile URL. No API key required."
    )
    args_schema: Type[BaseModel] = ICIJInput

    def _reconcile(self, name: str) -> List[Dict]:
        queries = {f"q_{ds}": {"query": name, "limit": 5} for ds in _ICIJ_DATASETS}
        data = _icij_request("POST", ICIJ_RECONCILE_URL, {"queries": queries})
        if not data:
            return []
        seen_ids: set = set()
        candidates = []
        for key, result_block in data.items():
            dataset_name = key.replace("q_", "")
            for r in result_block.get("result", []):
                node_id = str(r.get("id", ""))
                if not node_id or node_id in seen_ids:
                    continue
                seen_ids.add(node_id)
                raw_type = r.get("type", [{}])
                type_str = raw_type[0].get("id", "") if isinstance(raw_type, list) and raw_type else ""
                candidates.append({
                    "id": node_id, "name": r.get("name", name),
                    "score": r.get("score", 0), "dataset": dataset_name,
                    "type_label": _ICIJ_TYPE_MAP.get(type_str, type_str.split("/")[-1].title()),
                    "profile_url": ICIJ_NODE_PAGE_URL.format(node_id=node_id),
                })
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:5]

    def _run(self, name: str, country_code: str = "") -> str:
        time.sleep(1.0)
        candidates = self._reconcile(name)
        if not candidates:
            return (
                f"ICIJ_RESULT: No matches for '{name}' across all ICIJ datasets.\n"
                f"ICIJ_CLEAN: Entity not present in any ICIJ investigation dataset.\n"
                f"ICIJ_OFFSHORE_EXPOSURE: NO"
            )

        quoted_name = requests.utils.quote(name)
        output_blocks = [
            f"ICIJ_RESULT: {len(candidates)} match(es) found for '{name}'.",
            f"ICIJ_SEARCH_URL: https://offshoreleaks.icij.org/search?q={quoted_name}", "",
        ]

        for rank, cand in enumerate(candidates, 1):
            node_id = cand["id"]
            time.sleep(1.2)
            detail = _icij_request("GET", ICIJ_REST_NODE_URL.format(node_id=node_id)) or {}

            node_name = detail.get("name") or cand["name"]
            jurisdiction = detail.get("jurisdiction") or detail.get("country_codes") or "N/A"
            incorp_date = detail.get("incorporation_date") or "N/A"
            status = detail.get("status") or "N/A"
            source_id = detail.get("sourceID") or cand["dataset"].replace("-", " ").title()
            status_flag = " STRUCK OFF / INACTIVE" if isinstance(status, str) and status.lower() in (
                "defaulted", "struck off", "dissolved", "inactive") else ""
            score_str = f"{cand['score']:.2f}" if isinstance(cand["score"], float) else str(cand["score"])

            block_lines = [
                f"### Match #{rank}: {node_name}",
                f"- **Type**: {cand['type_label']}",
                f"- **Dataset**: {cand['dataset'].replace('-', ' ').title()} (source: {source_id})",
                f"- **Match Score**: {score_str}",
                f"- **Jurisdiction**: {jurisdiction}",
                f"- **Incorporated**: {incorp_date}",
                f"- **Status**: {status}{status_flag}",
                f"- **Profile URL**: {cand['profile_url']}",
                f"- **ICIJ_NODE_ID**: {node_id}",
            ]

            time.sleep(1.0)
            rels_data = _icij_request("GET", ICIJ_REST_RELS_URL.format(node_id=node_id)) or {}
            raw_rels = rels_data.get("relationships", rels_data if isinstance(rels_data, list) else [])
            raw_nodes = {str(n.get("id")): n for n in rels_data.get("nodes", [])}
            rels = []
            for rel in raw_rels[:10]:
                rel_type = rel.get("rel_type") or rel.get("type") or rel.get("relationship", "connected")
                linked_id = str(rel.get("end_node_id") or rel.get("endNodeId") or
                                rel.get("start_node_id") or rel.get("startNodeId") or "")
                linked_node = raw_nodes.get(linked_id, {})
                linked_name = linked_node.get("name") or linked_node.get("caption") or linked_id
                linked_type_raw = (linked_node.get("labels") or [""])[0]
                linked_type = _ICIJ_TYPE_MAP.get(
                    f"https://offshoreleaks.icij.org/schema/oldb/{linked_type_raw.lower()}",
                    linked_type_raw or "Node",
                )
                rels.append((rel_type, linked_id, linked_name, linked_type,
                              _ICIJ_REL_RISK.get(rel_type.lower(), rel_type)))

            if rels:
                block_lines.append("- **Relationships**:")
                for rel_type, linked_id, linked_name, linked_type, risk_note in rels:
                    linked_url = ICIJ_NODE_PAGE_URL.format(node_id=linked_id) if linked_id else ""
                    block_lines.append(
                        f"  - `{rel_type}` → **{linked_name}** ({linked_type}) — {risk_note}"
                        + (f"  [{linked_url}]({linked_url})" if linked_url else "")
                    )
            else:
                block_lines.append("- **Relationships**: none returned by API")

            output_blocks.append("\n".join(block_lines))
            output_blocks.append("")

        top = candidates[0]
        datasets_found = list(dict.fromkeys(c["dataset"].replace("-", " ").title() for c in candidates))
        output_blocks.append(
            f"ICIJ_TOP_MATCH: {top['name']} | Dataset: {top['dataset'].replace('-', ' ').title()} | "
            f"Score: {top['score']} | URL: {top['profile_url']}"
        )
        output_blocks.append(f"ICIJ_OFFSHORE_EXPOSURE: YES — {', '.join(datasets_found)}")
        return "\n".join(output_blocks)


# ---------------------------------------------------------------------------
# NewsAPI
# ---------------------------------------------------------------------------

try:
    from crewai_tools import NewsApiTool as _CrewAINewsApiTool
    _NEWSAPI_AVAILABLE = True
except ImportError:
    _NEWSAPI_AVAILABLE = False
    _CrewAINewsApiTool = None


def _build_news_api_tool():
    if not _NEWSAPI_AVAILABLE or not os.getenv("NEWS_API_KEY"):
        return None
    try:
        return _CrewAINewsApiTool()
    except Exception:
        return None


news_api_tool = _build_news_api_tool()


class NewsApiEntityInput(BaseModel):
    entity_name: str = Field(..., description="Full name of the person or organisation.")
    context: str = Field(default="", description="Optional context keywords (e.g. 'sanctions', 'fraud').")
    max_results: int = Field(default=5, description="Maximum number of articles (1-10).")


class NewsApiEntitySearchTool(BaseTool):
    """AML-oriented news search backed by NewsAPI.org for structured article retrieval."""

    name: str = "NewsAPI Entity Search"
    description: str = (
        "Searches NewsAPI.org for recent news about a specific person or organisation. "
        "Best for: AML adverse-media checks, sanctions confirmation, corporate investigations. "
        "Input: entity_name (required), context keywords (optional), max_results (optional, 1-10). "
        "Returns article title, source, publication date, and URL. Requires NEWS_API_KEY env var."
    )
    args_schema: Type[BaseModel] = NewsApiEntityInput

    def _run(self, entity_name: str, context: str = "", max_results: int = 5) -> str:
        if not _NEWSAPI_AVAILABLE:
            return "NEWS_API_ERROR: crewai-tools not installed. Run: pip install crewai-tools newsapi-python"
        if not os.getenv("NEWS_API_KEY"):
            return "NEWS_API_ERROR: NEWS_API_KEY not set. Get a key at https://newsapi.org"

        query_parts = [f'"{entity_name}"']
        if context.strip():
            query_parts.append(context.strip())
        query = " ".join(query_parts)

        try:
            tool_instance = _CrewAINewsApiTool()
            raw = tool_instance._run(query)

            # Parse the raw output into structured article blocks.
            # CrewAI's NewsApiTool returns a string of article dicts or a JSON list.
            articles = []
            try:
                import json as _json
                parsed = _json.loads(raw)
                if isinstance(parsed, list):
                    articles = parsed
                elif isinstance(parsed, dict) and "articles" in parsed:
                    articles = parsed["articles"]
            except Exception:
                pass

            if articles:
                max_results = min(max(1, max_results), 10)
                lines = [f"NewsAPI results for: {entity_name}" + (f" [{context}]" if context else ""), ""]
                for i, art in enumerate(articles[:max_results], 1):
                    title   = (art.get("title")   or "").strip()
                    source  = (art.get("source", {}).get("name") or art.get("source") or "Unknown").strip()
                    pub_at  = (art.get("publishedAt") or art.get("published_at") or "")[:10]
                    url     = (art.get("url")     or "").strip()
                    desc    = (art.get("description") or art.get("content") or "")[:200].strip()
                    lines.append(
                        f"[{i}] {title}\n"
                        f"    Source: {source} | Date: {pub_at}\n"
                        + (f"    Summary: {desc}\n" if desc else "")
                        + f"    URL: {url}"
                    )
                return "\n".join(lines)
            
            if len(raw) > 3000:
                raw = raw[:3000] + "\n... [truncated]"
            return raw
        except Exception as e:
            return f"NEWS_API_ERROR: {e}"