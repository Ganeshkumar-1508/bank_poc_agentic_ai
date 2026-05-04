#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to verify the JSON input normalization fix for malformed tool calls.
Tests the _normalize_tool_input function in search_tool.py
"""

import sys
import os

# Add Test directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_normalize_tool_input():
    """Test the _normalize_tool_input function from search_tool.py"""
    print("=" * 70)
    print("Testing search_tool._normalize_tool_input()")
    print("=" * 70)
    
    from tools.search_tool import _normalize_tool_input
    
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
                print(f"       Input: {input_data!r}")
                print(f"       Output: {result}")
                passed += 1
            else:
                print(f"[FAIL] Test {i}: {description}")
                print(f"       Input: {input_data!r}")
                print(f"       Expected: {expected}")
                print(f"       Got: {result}")
                failed += 1
        except Exception as e:
            print(f"[FAIL] Test {i}: {description}")
            print(f"       Input: {input_data!r}")
            print(f"       Error: {e}")
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
            print(f"       Input: {input_data!r}")
            print(f"       Expected ValueError, got: {result}")
            failed += 1
        except ValueError as e:
            print(f"[PASS] Error Test {i}: {description}")
            print(f"       Input: {input_data!r}")
            print(f"       Correctly raised ValueError: {e}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] Error Test {i}: {description}")
            print(f"       Input: {input_data!r}")
            print(f"       Expected ValueError, got {type(e).__name__}: {e}")
            failed += 1
        print()
    
    print("=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("JSON INPUT NORMALIZATION FIX VERIFICATION TESTS")
    print("=" * 70 + "\n")
    
    success = test_normalize_tool_input()
    
    if success:
        print("\n[SUCCESS] All tests passed!")
        sys.exit(0)
    else:
        print("\n[FAILURE] Some tests failed!")
        sys.exit(1)
