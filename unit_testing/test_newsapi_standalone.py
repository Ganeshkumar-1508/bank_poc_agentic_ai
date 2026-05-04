#!/usr/bin/env python3
"""
Test NewsAPI Entity Search - alternative to GDELT for adverse media screening
"""
import os
import sys
import json

# Load environment variables
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

NEWS_API_KEY = os.getenv("NEWS_API_KEY")

if not NEWS_API_KEY:
    print("ERROR: NEWS_API_KEY not found in .env file")
    sys.exit(1)

print("=" * 60)
print("Testing NewsAPI Entity Search")
print("=" * 60)

import requests

# NewsAPI search endpoint
NEWSAPI_BASE = "https://newsapi.org/v2/everything"

query = '"Tony Blair" sanctions OR adverse OR fraud OR corruption'
params = {
    "q": query,
    "apiKey": NEWS_API_KEY,
    "language": "en",
    "sortBy": "relevancy",
    "pageSize": 5,
}

print(f"\nQuery: {query}")
print("Fetching from NewsAPI...\n")

try:
    resp = requests.get(NEWSAPI_BASE, params=params, timeout=15)
    print(f"Status Code: {resp.status_code}")

    if resp.status_code != 200:
        print(f"Error response: {resp.text}")
        sys.exit(1)

    data = resp.json()
    articles = data.get("articles", [])

    if not articles:
        print("No NewsAPI results found.")
        sys.exit(0)

    print(f"Found {len(articles)} articles:\n")
    print("=" * 60)

    for i, art in enumerate(articles[:5], 1):
        title = art.get("title", "No title")
        source = art.get("source", {}).get("name", "Unknown")
        published = art.get("publishedAt", "Unknown date")[:10]
        url = art.get("url", "No URL")
        desc = (art.get("description") or "")[:150]

        print(f"\n[{i}] {title}")
        print(f"    Source: {source} | Date: {published}")
        if desc:
            print(f"    Summary: {desc}...")
        print(f"    URL: {url}")
        print("-" * 60)

    print("\n" + "=" * 60)
    print("SUCCESS: NewsAPI search worked!")
    print("=" * 60)

except requests.exceptions.RequestException as e:
    print(f"\nERROR: Request failed: {e}")
    print("\n" + "=" * 60)
    print("FAILED: NewsAPI search encountered a network error")
    print("=" * 60)
    sys.exit(1)
except Exception as e:
    print(f"\nERROR: {type(e).__name__}: {e}")
    print("\n" + "=" * 60)
    print("FAILED: NewsAPI search encountered an error")
    print("=" * 60)
    sys.exit(1)
