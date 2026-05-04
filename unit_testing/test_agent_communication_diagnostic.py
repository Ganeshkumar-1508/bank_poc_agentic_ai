#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Diagnostic test for agent communication - validates the fix integration
without requiring crewai to be installed.
"""

import sys
import os
import json
import re

# Add Test directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_json_normalization_integration():
    """Test that JSON normalization works in the search_tool context"""
    print("=" * 70)
    print("TEST: JSON Normalization Integration")
    print("=" * 70)
    
    # Import the function directly from search_tool (bypassing crewai import)
    import importlib.util
    spec = importlib.util.spec_from_file_location("search_tool", "tools/search_tool.py")
    
    # We need to mock the crewai import
    import sys
    from unittest.mock import MagicMock
    sys.modules['crewai'] = MagicMock()
    sys.modules['crewai.tools'] = MagicMock()
    
    try:
        from tools.search_tool import _normalize_tool_input
        
        # Test the malformed JSON pattern that was causing issues
        malformed_input = [{"query": "Analyze Fixed Deposit rates for India with 85 months tenure"}, ["result"]]
        result = _normalize_tool_input(malformed_input)
        
        expected = {"query": "Analyze Fixed Deposit rates for India with 85 months tenure", "max_results": 5}
        
        if result == expected:
            print(f"[PASS] JSON normalization correctly handles malformed input")
            print(f"  Input: {malformed_input}")
            print(f"  Output: {result}")
            return True
        else:
            print(f"[FAIL] JSON normalization failed")
            print(f"  Input: {malformed_input}")
            print(f"  Expected: {expected}")
            print(f"  Got: {result}")
            return False
    except Exception as e:
        print(f"[FAIL] Error during JSON normalization test: {e}")
        return False


def test_url_validation_integration():
    """Test that URL validation works correctly"""
    print()
    print("=" * 70)
    print("TEST: URL Validation Integration")
    print("=" * 70)
    
    # Import the function directly from url_validation_tool
    import importlib.util
    from unittest.mock import MagicMock
    
    # Mock crewai_tools
    sys.modules['crewai_tools'] = MagicMock()
    
    try:
        from tools.url_validation_tool import validate_urls_tool_func
        
        # Test content with mixed valid/invalid URLs
        test_content = """
        Search Results:
        1. [SBI FD Rates](https://www.sbi.co.in/articleshow/12345678)
        2. [Fake News](https://hallucinated-url.xyz/fake)
        3. [HDFC Article](https://www.hdfc.com/news/2026/01/15/story)
        4. [Empty Link]()
        """
        
        result = validate_urls_tool_func(test_content)
        
        # Check that valid URLs are preserved
        valid_checks = [
            r"\[SBI FD Rates\]\(https://www\.sbi\.co\.in/articleshow/12345678\)",
            r"\[HDFC Article\]\(https://www\.hdfc\.com/news/2026/01/15/story\)",
        ]
        
        # Check that invalid URLs are removed
        invalid_checks = [
            r"\*\*Fake News\*\* \(URL removed: invalid format\)",
            r"\*\*Empty Link\*\* \(no URL available\)",
        ]
        
        all_passed = True
        for pattern in valid_checks:
            if re.search(pattern, result):
                print(f"[PASS] Valid URL preserved: {pattern}")
            else:
                print(f"[FAIL] Valid URL not preserved: {pattern}")
                all_passed = False
        
        for pattern in invalid_checks:
            if re.search(pattern, result):
                print(f"[PASS] Invalid URL removed: {pattern}")
            else:
                print(f"[FAIL] Invalid URL not removed: {pattern}")
                all_passed = False
        
        return all_passed
    except Exception as e:
        print(f"[FAIL] Error during URL validation test: {e}")
        return False


def test_module_verification_integration():
    """Test that module verification works correctly"""
    print()
    print("=" * 70)
    print("TEST: Module Verification Integration")
    print("=" * 70)
    
    try:
        from utils.module_verifier import verify_module, get_missing_modules
        
        # Test verifying installed modules
        test_modules = ["json", "re", "sys", "os", "nonexistent_module_xyz"]
        results = verify_module("json")
        
        if results:
            print(f"[PASS] verify_module correctly identifies installed modules")
        else:
            print(f"[FAIL] verify_module failed to identify installed module 'json'")
            return False
        
        # Test get_missing_modules
        missing = get_missing_modules(test_modules)
        
        if "nonexistent_module_xyz" in missing and "json" not in missing:
            print(f"[PASS] get_missing_modules correctly identifies missing modules")
            print(f"  Missing: {missing}")
            return True
        else:
            print(f"[FAIL] get_missing_modules incorrect results")
            print(f"  Missing: {missing}")
            return False
    except Exception as e:
        print(f"[FAIL] Error during module verification test: {e}")
        return False


def test_agent_data_flow():
    """Test the data flow between agents (simulated)"""
    print()
    print("=" * 70)
    print("TEST: Agent Data Flow (Simulated)")
    print("=" * 70)
    
    # Simulate the data flow that would happen between agents
    # 1. User query comes in
    user_query = "Analyze Fixed Deposit rates for India with 85 months tenure"
    
    # 2. Router agent processes the query
    # (simulated - would normally use crewai)
    routing_decision = {
        "intent": "fd_advisor",
        "region": "India",
        "tenure_months": 85,
        "product_type": "FD"
    }
    
    # 3. Research agent searches for information
    # (simulated - would use search_tool with JSON normalization)
    search_input = [{"query": f"FD rates India {routing_decision['tenure_months']} months"}, ["result"]]
    
    # Test JSON normalization
    try:
        from unittest.mock import MagicMock
        sys.modules['crewai'] = MagicMock()
        sys.modules['crewai.tools'] = MagicMock()
        from tools.search_tool import _normalize_tool_input
        
        normalized = _normalize_tool_input(search_input)
        
        if normalized["query"] == f"FD rates India {routing_decision['tenure_months']} months":
            print(f"[PASS] Data flow: JSON normalization works in agent context")
            print(f"  Original: {search_input}")
            print(f"  Normalized: {normalized}")
        else:
            print(f"[FAIL] Data flow: JSON normalization failed")
            return False
    except Exception as e:
        print(f"[FAIL] Data flow error: {e}")
        return False
    
    # 4. Summary agent compiles results with URL validation
    # (simulated - would use url_validation_tool)
    try:
        from tools.url_validation_tool import validate_urls_tool_func
        
        compiled_results = f"""
        FD Rates for India ({routing_decision['tenure_months']} months):
        1. [SBI FD Rates](https://www.sbi.co.in/articleshow/12345678)
        2. [HDFC FD Rates](https://www.hdfc.com/news/2026/01/15/fd-rates)
        """
        
        validated = validate_urls_tool_func(compiled_results)
        
        if "[SBI FD Rates]" in validated and "[HDFC FD Rates]" in validated:
            print(f"[PASS] Data flow: URL validation works in agent context")
        else:
            print(f"[FAIL] Data flow: URL validation failed")
            return False
    except Exception as e:
        print(f"[FAIL] Data flow error: {e}")
        return False
    
    # 5. Module verification ensures dependencies are available
    try:
        from utils.module_verifier import verify_module
        
        required_modules = ["json", "re", "requests"]
        all_installed = all(verify_module(m) for m in required_modules)
        
        if all_installed:
            print(f"[PASS] Data flow: Module verification confirms dependencies")
        else:
            print(f"[WARN] Data flow: Some required modules missing")
    except Exception as e:
        print(f"[FAIL] Data flow error: {e}")
        return False
    
    return True


def main():
    """Run all diagnostic tests"""
    print()
    print("=" * 70)
    print("AGENT COMMUNICATION DIAGNOSTIC TESTS")
    print("Validating fixes without crewai dependency")
    print("=" * 70)
    print()
    
    results = []
    
    # Run tests
    results.append(("JSON Normalization Integration", test_json_normalization_integration()))
    results.append(("URL Validation Integration", test_url_validation_integration()))
    results.append(("Module Verification Integration", test_module_verification_integration()))
    results.append(("Agent Data Flow (Simulated)", test_agent_data_flow()))
    
    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} {name}")
    
    print()
    print(f"Total: {passed}/{total} tests passed")
    
    if passed == total:
        print()
        print("All agent communication fixes are working correctly!")
        print("Note: Full end-to-end testing requires crewai installation.")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
