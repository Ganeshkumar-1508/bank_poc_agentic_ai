#!/usr/bin/env python3
"""Network connectivity diagnostic for GDELT vs NewsAPI"""
import socket
import requests
import sys

# Fix for Windows console encoding
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")

print("=" * 60)
print("NETWORK CONNECTIVITY DIAGNOSTIC")
print("=" * 60)

# Test DNS resolution
print("\n1. DNS Resolution Test:")
print("-" * 40)

for domain in ["api.gdeltproject.org", "newsapi.org"]:
    try:
        ip = socket.gethostbyname(domain)
        print(f"  [OK] {domain}: DNS resolved to {ip}")
    except Exception as e:
        print(f"  [FAIL] {domain}: DNS failed - {e}")

# Test HTTP connectivity
print("\n2. HTTP Connectivity Test (5 second timeout):")
print("-" * 40)

tests = [
    (
        "GDELT API",
        "https://api.gdeltproject.org/api/v2/doc/doc",
        {"query": "test", "mode": "artlist", "format": "json", "maxrecords": 1},
    ),
    (
        "NewsAPI",
        "https://newsapi.org/v2/top-headlines",
        {"country": "us", "apiKey": "test"},
    ),
]

for name, url, params in tests:
    try:
        resp = requests.get(url, params=params, timeout=5)
        print(f"  [OK] {name}: Connected (Status: {resp.status_code})")
    except requests.exceptions.Timeout:
        print(f"  [FAIL] {name}: Connection timed out (>5s)")
    except requests.exceptions.ConnectionError as e:
        print(f"  [FAIL] {name}: Connection failed - {type(e).__name__}")
    except Exception as e:
        print(f"  [?] {name}: Other error - {type(e).__name__}: {e}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
