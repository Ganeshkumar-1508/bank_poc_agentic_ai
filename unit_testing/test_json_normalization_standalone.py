#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Standalone test for JSON input normalization - no crewai dependency.
Tests the _normalize_tool_input function logic directly.
"""

import json
import re
from typing import Dict, Any, Union

def _normalize_tool_input(input_data: Any) -> Dict[str, Any]:
    """
    Normalize malformed LLM tool call inputs to valid dict format.
    Copied from search_tool.py for standalone testing.
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
            parsed = json.loads(input_data)
            return _normalize_tool_input(parsed)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON-like pattern from string
        json_pattern = r'\[?\s*\{\s*"query"\s*:\s*"([^"]+)"\s*(?:,\s*"max_results"\s*:\s*(\d+))?\s*\}\s*\]?'
        match = re.search(json_pattern, input_data)
        if match:
            query = match.group(1)
            max_results = int(match.group(2)) if match.group(2) else 5
            return {"query": query, "max_results": max_results}

        # If it's just a plain string, treat it as the query
        if input_data.strip():
            return {"query": input_data.strip(), "max_results": 5}

    raise ValueError(f"Unable to normalize input: {input_data!r}")


def test_normalize_tool_input():
    """Test the _normalize_tool_input function"""
    print("=" * 70)
    print("Testing JSON Input Normalization (Standalone)")
    print("=" * 70)

    test_cases = [
        # (input, expected_output, description)
        (
            {"query": "SBI FD rates 2026", "max_results": 5},
            {"query": "SBI FD rates 2026", "max_results": 5},
            "Valid dict input"
        ),
        (
            [{"query": "SBI FD rates 2026", "max_results": 5}, ["result"]],
            {"query": "SBI FD rates 2026", "max_results": 5},
            "Malformed JSON pattern: [{'query': ..., 'max_results': 5}, ['result']]"
        ),
        (
            [{"query": "HDFC Bank news"}],
            {"query": "HDFC Bank news", "max_results": 5},
            "Malformed: list with single dict (missing max_results)"
        ),
        (
            '{"query": "ICICI credit rating", "max_results": 3}',
            {"query": "ICICI credit rating", "max_results": 3},
            "JSON string input"
        ),
        (
            '[{"query": "Axis Bank NPA 2026", "max_results": 7}]',
            {"query": "Axis Bank NPA 2026", "max_results": 7},
            "JSON string: list with dict"
        ),
        (
            "Kotak Mahindra FD rates",
            {"query": "Kotak Mahindra FD rates", "max_results": 5},
            "Plain string input (treated as query)"
        ),
        (
            {"query": "Bajaj Finance rates", "max_results": 10},
            {"query": "Bajaj Finance rates", "max_results": 10},
            "Valid dict with max_results=10"
        ),
    ]

    passed = 0
    failed = 0

    for i, (input_data, expected, description) in enumerate(test_cases, 1):
        try:
            result = _normalize_tool_input(input_data)
            if result == expected:
                print(f"[PASS] Test {i}: {description}")
                print(f"  Input: {input_data!r}")
                print(f"  Output: {result}")
                passed += 1
            else:
                print(f"[FAIL] Test {i}: {description}")
                print(f"  Input: {input_data!r}")
                print(f"  Expected: {expected}")
                print(f"  Got: {result}")
                failed += 1
        except Exception as e:
            print(f"[FAIL] Test {i}: {description}")
            print(f"  Input: {input_data!r}")
            print(f"  Error: {e}")
            failed += 1
        print()

    # Test error cases
    print("-" * 70)
    print("Testing error cases (should raise ValueError):")
    print("-" * 70)

    error_cases = [
        ({"invalid_key": "value"}, "Dict without 'query' key"),
        ([], "Empty list"),
        ([{"invalid_key": "value"}], "List with dict missing 'query'"),
        ("", "Empty string"),
        (123, "Integer input"),
        (None, "None input"),
    ]

    for i, (input_data, description) in enumerate(error_cases, 1):
        try:
            result = _normalize_tool_input(input_data)
            print(f"[FAIL] Error Test {i}: {description}")
            print(f"  Input: {input_data!r}")
            print(f"  Expected: ValueError")
            print(f"  Got: {result}")
            failed += 1
        except ValueError as e:
            print(f"[PASS] Error Test {i}: {description}")
            print(f"  Input: {input_data!r}")
            print(f"  Raised ValueError: {e}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] Error Test {i}: {description}")
            print(f"  Input: {input_data!r}")
            print(f"  Expected: ValueError, Got: {type(e).__name__}: {e}")
            failed += 1
        print()

    print("=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = test_normalize_tool_input()
    exit(0 if success else 1)
