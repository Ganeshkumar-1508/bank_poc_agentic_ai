#!/usr/bin/env python3
"""
Standalone test for GDELT search - bypasses crewai dependency
"""
import sys
import os
import time
import random
import requests

# GDELT API configuration
GDELT_API_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
_GDELT_LOW_VALUE = {"wikipedia.org", "reddit.com", "quora.com", "answers.yahoo.com"}
_gdelt_last_call_ts: float = 0.0
_GDELT_MIN_INTERVAL: float = 2.0

_GDELT_TIMESPAN_MAP = {
    "1y": "12months",
    "2y": "12months",
    "6m": "6months",
    "3m": "3months",
    "1m": "1months",
    "12months": "12months",
    "6months": "6months",
    "3months": "3months",
    "1months": "1months",
    "30d": "30d",
    "14d": "14d",
    "7d": "7d",
    "12w": "12w",
    "4w": "4w",
    "1w": "1w",
}


def _gdelt_wait_for_slot() -> None:
    global _gdelt_last_call_ts
    elapsed = time.monotonic() - _gdelt_last_call_ts
    if elapsed < _GDELT_MIN_INTERVAL:
        time.sleep(_GDELT_MIN_INTERVAL - elapsed + random.uniform(0.1, 0.5))
    _gdelt_last_call_ts = time.monotonic()


def _gdelt_fetch(query: str, max_records: int = 8, timespan: str = "6months") -> str:
    timespan = _GDELT_TIMESPAN_MAP.get(timespan.lower().strip(), timespan)
    retry_waits = [3, 8, 15]

    for attempt in range(4):
        _gdelt_wait_for_slot()
        try:
            resp = requests.get(
                GDELT_API_BASE,
                params={
                    "query": query,
                    "mode": "artlist",
                    "format": "json",
                    "maxrecords": max_records,
                    "timespan": timespan,
                    "sort": "relevance",
                },
                timeout=20,
            )
            if resp.status_code == 429:
                wait = max(
                    int(resp.headers.get("Retry-After", retry_waits[attempt])),
                    retry_waits[attempt],
                ) + random.uniform(0.1, 0.5)
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
                    + (f" | Tone: {tone_label}" if tone_label else "")
                    + "\n"
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


# Now test the function
print("=" * 60)
print("Testing GDELT News Search (_gdelt_fetch function)")
print("=" * 60)

query = '"Tony Blair" sanctions'
print(f"\nQuery: {query}")
print("Fetching from GDELT API...\n")

try:
    result = _gdelt_fetch(query, max_records=5, timespan="12months")
    print(result)
    print("\n" + "=" * 60)
    print("SUCCESS: GDELT search worked!")
    print("=" * 60)
except Exception as e:
    print(f"\nERROR: {type(e).__name__}: {e}")
    print("\n" + "=" * 60)
    print("FAILED: GDELT search encountered an error")
    print("=" * 60)
    sys.exit(1)
