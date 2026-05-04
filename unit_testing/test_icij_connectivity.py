#!/usr/bin/env python3
"""Quick ICIJ API connectivity test"""
import requests

print("Testing ICIJ API connectivity...")
print("-" * 40)

try:
    resp = requests.post(
        "https://reconcile.offshoreleaks.icij.org/reconcile",
        json={"queries": {"q_test": {"query": "test", "limit": 1}}},
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=15,
    )
    print(f"Status Code: {resp.status_code}")
    print(f"Response: {resp.text[:300] if resp.text else 'Empty'}")
except requests.exceptions.Timeout:
    print("ERROR: Connection timed out (API unreachable)")
except requests.exceptions.ConnectionError as e:
    print(f"ERROR: Connection failed - {e}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

print("-" * 40)
