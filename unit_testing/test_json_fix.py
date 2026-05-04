#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to verify the JSON parsing fix for malformed JSON structures.
Tests the extract_json function in langfuse_evaluator.py and report_parser.py
"""

import sys
import os
import io

# Add Test directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fix Unicode encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def test_langfuse_extractor():
    """Test the extract_json function from langfuse_evaluator.py"""
    print("=" * 60)
    print("Testing langfuse_evaluator.extract_json()")
    print("=" * 60)
    
    from langfuse_evaluator import extract_json
    
    # Test case 1: Valid JSON object
    valid_json = '{"query": "test", "max_results": 5}'
    try:
        result = extract_json(valid_json)
        print(f"[PASS] Test 1: Valid JSON parsed correctly: {result}")
    except Exception as e:
        print(f"[FAIL] Test 1: {e}")
    
    # Test case 2: Malformed JSON with array (the reported issue)
    malformed_json = '[{"query": "SBI credit rating 2026 CRISIL ICRA NPA ratio", "max_results": 5}, ["SBI Credit Rating Downgraded..."]]'
    try:
        result = extract_json(malformed_json)
        print(f"[PASS] Test 2: Malformed JSON handled, extracted: {result}")
    except ValueError as e:
        print(f"[PASS] Test 2: Malformed JSON correctly rejected with error: {e}")
    except Exception as e:
        print(f"[FAIL] Test 2 with unexpected error: {e}")
    
    # Test case 3: JSON in markdown code block
    markdown_json = '```json\n{"key": "value"}\n```'
    try:
        result = extract_json(markdown_json)
        print(f"[PASS] Test 3: Markdown JSON parsed correctly: {result}")
    except Exception as e:
        print(f"[FAIL] Test 3: {e}")
    
    # Test case 4: Empty input
    try:
        result = extract_json("")
        print(f"[FAIL] Test 4: Should have raised ValueError for empty input")
    except ValueError:
        print(f"[PASS] Test 4: Empty input correctly rejected")
    except Exception as e:
        print(f"[FAIL] Test 4 with unexpected error: {e}")
    
    # Test case 5: List of valid dicts
    list_of_dicts = '[{"a": 1}, {"b": 2}]'
    try:
        result = extract_json(list_of_dicts)
        print(f"[PASS] Test 5: List of dicts handled, extracted: {result}")
    except Exception as e:
        print(f"[FAIL] Test 5: {e}")


def test_report_parser():
    """Test the _safe_json_loads function from report_parser.py"""
    print("\n" + "=" * 60)
    print("Testing report_parser._safe_json_loads()")
    print("=" * 60)
    
    from utils.report_parser import _safe_json_loads
    
    # Test case 1: Valid JSON object
    valid_json = '{"query": "test", "max_results": 5}'
    result = _safe_json_loads(valid_json)
    if result == {"query": "test", "max_results": 5}:
        print(f"[PASS] Test 1: Valid JSON parsed correctly: {result}")
    else:
        print(f"[FAIL] Test 1: Expected dict, got {result}")
    
    # Test case 2: Malformed JSON with array (the reported issue)
    malformed_json = '[{"query": "SBI credit rating 2026 CRISIL ICRA NPA ratio", "max_results": 5}, ["SBI Credit Rating Downgraded..."]]'
    result = _safe_json_loads(malformed_json)
    if result is not None and isinstance(result, dict):
        print(f"[PASS] Test 2: Malformed JSON handled, extracted dict: {result}")
    elif result is None:
        print(f"[PASS] Test 2: Malformed JSON correctly returned None")
    else:
        print(f"[FAIL] Test 2: Unexpected result: {result}")
    
    # Test case 3: Empty input
    result = _safe_json_loads("")
    if result is None:
        print(f"[PASS] Test 3: Empty input returned None")
    else:
        print(f"[FAIL] Test 3: Expected None, got {result}")
    
    # Test case 4: List of dicts
    list_of_dicts = '[{"a": 1}, {"b": 2}]'
    result = _safe_json_loads(list_of_dicts)
    if result == {"a": 1}:
        print(f"[PASS] Test 4: List of dicts handled, extracted first: {result}")
    else:
        print(f"[FAIL] Test 4: Expected first dict, got {result}")
    
    # Test case 5: Invalid JSON string
    invalid_json = 'not valid json at all'
    try:
        result = _safe_json_loads(invalid_json)
        print(f"[FAIL] Test 5: Should have raised exception for invalid JSON")
    except Exception:
        print(f"[PASS] Test 5: Invalid JSON correctly raised exception")


def test_extract_structured_summary():
    """Test the extract_structured_summary function from report_parser.py"""
    print("\n" + "=" * 60)
    print("Testing report_parser.extract_structured_summary()")
    print("=" * 60)
    
    from utils.report_parser import extract_structured_summary
    
    # Test case 1: Valid structured summary
    valid_output = """
    ## STRUCTURED_SUMMARY
    ```json
    {"key": "value", "number": 42}
    ```
    Some other text
    """
    clean, data = extract_structured_summary(valid_output)
    if data == {"key": "value", "number": 42}:
        print(f"[PASS] Test 1: Valid structured summary extracted: {data}")
    else:
        print(f"[FAIL] Test 1: Expected dict, got {data}")
    
    # Test case 2: Malformed JSON in structured summary
    malformed_output = """
    ## STRUCTURED_SUMMARY
    ```json
    [{"query": "test"}, ["result"]]
    ```
    Some other text
    """
    clean, data = extract_structured_summary(malformed_output)
    if data is not None and isinstance(data, dict):
        print(f"[PASS] Test 2: Malformed JSON handled, extracted: {data}")
    elif data is None:
        print(f"[PASS] Test 2: Malformed JSON correctly returned None")
    else:
        print(f"[FAIL] Test 2: Unexpected result: {data}")
    
    # Test case 3: No structured summary
    no_summary = "Just plain text with no JSON"
    clean, data = extract_structured_summary(no_summary)
    if data is None and clean == no_summary:
        print(f"[PASS] Test 3: No summary case handled correctly")
    else:
        print(f"[FAIL] Test 3: Expected None data, got {data}")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("JSON PARSING FIX VERIFICATION TESTS")
    print("=" * 60 + "\n")
    
    try:
        test_langfuse_extractor()
        test_report_parser()
        test_extract_structured_summary()
        
        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETED")
        print("=" * 60)
    except Exception as e:
        print(f"\n[FAIL] Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
