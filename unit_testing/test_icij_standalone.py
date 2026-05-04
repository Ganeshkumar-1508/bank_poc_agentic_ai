#!/usr/bin/env python3
"""
Standalone test for ICIJ Offshore Leaks Search Tool
Tests the ICIJ REST API directly without crewai dependencies
"""
import sys
import os
import time
import requests

# ICIJ API configuration (from news_tool.py)
ICIJ_RECONCILE_URL = "https://reconcile.offshoreleaks.icij.org/reconcile"
ICIJ_REST_NODE_URL = "https://offshoreleaks.icij.org/api/v1/nodes/{node_id}"
ICIJ_REST_RELS_URL = (
    "https://offshoreleaks.icij.org/api/v1/nodes/{node_id}/relationships"
)
ICIJ_NODE_PAGE_URL = "https://offshoreleaks.icij.org/nodes/{node_id}"

_Icij_DATASETS = [
    "offshoreleaks",
    "panamapapers",
    "pandorapapers",
    "paradise-papers",
    "bahamasleaks",
]
_Icij_TYPE_MAP = {
    "https://offshoreleaks.icij.org/schema/oldb/intermediary": "Intermediary",
    "https://offshoreleaks.icij.org/schema/oldb/entity": "Entity",
    "https://offshoreleaks.icij.org/schema/oldb/officer": "Officer",
    "https://offshoreleaks.icij.org/schema/oldb/agent": "Agent",
}


def _icij_request(method: str, url: str, payload=None, timeout=15):
    """Make request to ICIJ API with retry logic"""
    headers = {"Accept": "application/json", "User-Agent": "AMLComplianceBot/2.0"}
    for attempt in range(3):
        try:
            if method == "POST":
                headers["Content-Type"] = "application/json"
                resp = requests.post(
                    url, json=payload, headers=headers, timeout=timeout
                )
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


def test_icij_search(name: str, country_code: str = ""):
    """Test ICIJ search for a given name"""
    print("=" * 60)
    print(f"Testing ICIJ Offshore Leaks Search: '{name}'")
    print("=" * 60)

    # Build reconciliation query
    queries = {f"q_{ds}": {"query": name, "limit": 5} for ds in _Icij_DATASETS}

    print(f"\nSearching ICIJ datasets: {', '.join(_Icij_DATASETS)}")
    print("Sending request to ICIJ reconciliation API...")

    data = _icij_request("POST", ICIJ_RECONCILE_URL, {"queries": queries})

    if not data:
        print("\nERROR: ICIJ API returned no data or failed to respond.")
        return False

    # Parse results
    candidates = []
    seen_ids = set()

    for key, result_block in data.items():
        dataset_name = key.replace("q_", "")
        for r in result_block.get("result", []):
            node_id = str(r.get("id", ""))
            if not node_id or node_id in seen_ids:
                continue
            seen_ids.add(node_id)

            raw_type = r.get("type", [{}])
            type_str = (
                raw_type[0].get("id", "")
                if isinstance(raw_type, list) and raw_type
                else ""
            )

            candidates.append(
                {
                    "id": node_id,
                    "name": r.get("name", name),
                    "score": r.get("score", 0),
                    "dataset": dataset_name,
                    "type_label": _Icij_TYPE_MAP.get(
                        type_str,
                        type_str.split("/")[-1].title() if type_str else "Unknown",
                    ),
                    "profile_url": ICIJ_NODE_PAGE_URL.format(node_id=node_id),
                }
            )

    # Sort by score and take top 5
    candidates.sort(key=lambda x: x["score"], reverse=True)
    candidates = candidates[:5]

    if not candidates:
        print(f"\nNo matches found for '{name}' in ICIJ Offshore Leaks database.")
        print(
            "This is expected for individuals not involved in offshore leaks investigations."
        )
        return True

    print(f"\nFound {len(candidates)} match(es):")
    print("-" * 60)

    for rank, cand in enumerate(candidates, 1):
        print(f"\n[Match #{rank}] {cand['name']}")
        print(f"  Type: {cand['type_label']}")
        print(f"  Dataset: {cand['dataset']}")
        print(f"  Match Score: {cand['score']}")
        print(f"  Profile: {cand['profile_url']}")

        # Fetch details
        time.sleep(0.5)
        detail = (
            _icij_request("GET", ICIJ_REST_NODE_URL.format(node_id=cand["id"])) or {}
        )

        if detail:
            jurisdiction = (
                detail.get("jurisdiction") or detail.get("country_codes") or "N/A"
            )
            incorp_date = detail.get("incorporation_date") or "N/A"
            status = detail.get("status") or "N/A"
            source_id = (
                detail.get("sourceID") or cand["dataset"].replace("-", " ").title()
            )

            print(f"  Jurisdiction: {jurisdiction}")
            print(f"  Incorporated: {incorp_date}")
            print(f"  Status: {status}")
            print(f"  Source: {source_id}")

            # Fetch relationships
            time.sleep(0.5)
            rels_data = (
                _icij_request("GET", ICIJ_REST_RELS_URL.format(node_id=cand["id"]))
                or {}
            )
            raw_rels = rels_data.get(
                "relationships", rels_data if isinstance(rels_data, list) else []
            )
            raw_nodes = {str(n.get("id")): n for n in rels_data.get("nodes", [])}

            if raw_rels:
                print(f"  Relationships ({len(raw_rels[:5])} shown):")
                for rel in raw_rels[:5]:
                    rel_type = rel.get("rel_type") or rel.get("type") or "connected"
                    linked_id = str(
                        rel.get("end_node_id")
                        or rel.get("endNodeId")
                        or rel.get("start_node_id")
                        or rel.get("startNodeId")
                        or ""
                    )
                    linked_node = raw_nodes.get(linked_id, {})
                    linked_name = (
                        linked_node.get("name")
                        or linked_node.get("caption")
                        or linked_id
                    )
                    print(f"    - {rel_type}: {linked_name}")

    print("\n" + "=" * 60)
    print("SUCCESS: ICIJ Offshore Leaks search worked!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    # Test with a known offshore entity (e.g., from Panama Papers)
    test_name = "Mosack Fonseca"  # Well-known law firm from Panama Papers

    if len(sys.argv) > 1:
        test_name = sys.argv[1]

    success = test_icij_search(test_name)
    sys.exit(0 if success else 1)
