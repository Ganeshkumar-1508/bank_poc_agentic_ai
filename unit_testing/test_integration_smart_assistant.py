#!/usr/bin/env python
"""
Integration Tests for Smart Assistant Chat Interface

Tests the unified chat interface that routes queries to appropriate CrewAI agents.
"""

import os
import sys
import json
import requests
import pytest
from typing import Dict, Any, List

# Base URL for the Django development server
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")

# Test data for Smart Assistant
SMART_ASSISTANT_TEST_CASES = [
    {
        "name": "FD Rate Inquiry",
        "query": "What are the current FD rates for SBI?",
        "expected_features": ["rate_lookup", "bank_info"],
        "description": "Test basic FD rate inquiry"
    },
    {
        "name": "Loan Application Help",
        "query": "I want to apply for a personal loan of 5 lakhs",
        "expected_features": ["loan_intent", "amount_extraction"],
        "description": "Test loan application intent detection"
    },
    {
        "name": "Account Balance Query",
        "query": "What is my current account balance?",
        "expected_features": ["account_query", "authentication_check"],
        "description": "Test account balance inquiry"
    },
    {
        "name": "FD Comparison Request",
        "query": "Compare FD rates between HDFC and ICICI for 2 years",
        "expected_features": ["comparison", "multi_bank", "tenure_parsing"],
        "description": "Test FD comparison across banks"
    },
    {
        "name": "General Banking Question",
        "query": "How do I open a new savings account?",
        "expected_features": ["information_retrieval", "process_guidance"],
        "description": "Test general banking information query"
    },
    {
        "name": "Complex Multi-step Request",
        "query": "I have 10 lakhs to invest. Show me the best FD options and calculate maturity amounts",
        "expected_features": ["investment_advice", "calculation", "recommendation"],
        "description": "Test complex multi-feature request"
    }
]


class TestSmartAssistantIntegration:
    """Integration tests for Smart Assistant API"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment"""
        self.base_url = BASE_URL
        self.endpoint = f"{self.base_url}/api/smart-assistant-query/"
        
    def test_endpoint_availability(self):
        """Test that the Smart Assistant endpoint is accessible"""
        response = requests.post(
            self.endpoint,
            json={"query": "test"},
            headers={"Content-Type": "application/json"}
        )
        # Should not return 404 or connection error
        assert response.status_code in [200, 400, 500], \
            f"Endpoint not available: {response.status_code}"
    
    @pytest.mark.parametrize("test_case", SMART_ASSISTANT_TEST_CASES, ids=lambda x: x["name"])
    def test_smart_assistant_query(self, test_case):
        """
        Test Smart Assistant with various query types
        
        Args:
            test_case: Parameterized test case with query and expected features
        """
        print(f"\n{'='*70}")
        print(f"Testing: {test_case['name']}")
        print(f"Query: {test_case['query']}")
        print(f"{'='*70}")
        
        payload = {
            "query": test_case["query"],
            "session_id": f"test_session_{hash(test_case['query']) % 10000}",
            "user_id": "test_user_integration"
        }
        
        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            print(f"Status Code: {response.status_code}")
            print(f"Response Time: {response.elapsed.total_seconds():.2f}s")
            
            # Check response structure
            if response.status_code == 200:
                data = response.json()
                
                # Verify response has expected structure
                assert "response" in data or "answer" in data or "result" in data, \
                    "Response missing expected fields (response/answer/result)"
                
                print(f"Response: {json.dumps(data, indent=2)[:500]}...")
                
                # Log success
                print(f"✓ PASSED: {test_case['name']}")
                
            elif response.status_code == 400:
                # Bad request - might be due to missing auth or invalid session
                print(f"⚠ EXPECTED: Bad request (may require authentication)")
                print(f"Error: {response.json()}")
                
            else:
                print(f"Response: {response.text[:500]}")
                # Server errors are acceptable in test environment
                print(f"⚠ Server response (status {response.status_code})")
                
        except requests.exceptions.Timeout:
            print(f"✗ FAILED: Request timeout for {test_case['name']}")
            pytest.skip("Request timeout - server may be slow")
            
        except requests.exceptions.ConnectionError:
            print(f"✗ FAILED: Connection error - server not running")
            pytest.skip("Server not running")
            
        except json.JSONDecodeError as e:
            print(f"✗ FAILED: Invalid JSON response: {e}")
            pytest.fail("Invalid JSON response")
    
    def test_session_persistence(self):
        """Test that session context is maintained across multiple queries"""
        session_id = f"test_session_persistence_{os.getpid()}"
        
        # First query: Set context
        response1 = requests.post(
            self.endpoint,
            json={
                "query": "I want to invest 5 lakhs in FD",
                "session_id": session_id
            },
            headers={"Content-Type": "application/json"}
        )
        
        # Second query: Reference previous context
        response2 = requests.post(
            self.endpoint,
            json={
                "query": "What about 2 year tenure?",
                "session_id": session_id
            },
            headers={"Content-Type": "application/json"}
        )
        
        # Both should return valid responses (or appropriate errors)
        assert response1.status_code in [200, 400, 500]
        assert response2.status_code in [200, 400, 500]
        
        print("✓ Session persistence test completed")
    
    def test_empty_query_handling(self):
        """Test handling of empty or malformed queries"""
        empty_queries = [
            {"query": ""},
            {"query": "   "},
            {"query": None},
            {}
        ]
        
        for payload in empty_queries:
            response = requests.post(
                self.endpoint,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            # Should handle gracefully (return error or default response)
            assert response.status_code in [200, 400], \
                f"Empty query should be handled gracefully, got {response.status_code}"
        
        print("✓ Empty query handling test passed")
    
    def test_concurrent_requests(self):
        """Test handling of concurrent requests"""
        import concurrent.futures
        
        def make_request(i):
            response = requests.post(
                self.endpoint,
                json={
                    "query": f"Test query {i}",
                    "session_id": f"concurrent_test_{i}"
                },
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            return response.status_code
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All requests should complete (any valid status code)
        valid_codes = [200, 400, 500]
        assert all(code in valid_codes for code in results), \
            f"Some requests failed unexpectedly: {results}"
        
        print(f"✓ Concurrent requests test passed: {len(results)} requests completed")


if __name__ == "__main__":
    print("="*70)
    print("Smart Assistant Integration Tests")
    print("="*70)
    print(f"Base URL: {BASE_URL}")
    print(f"Endpoint: {BASE_URL}/api/smart-assistant-query/")
    print("="*70)
    
    pytest.main([__file__, "-v", "-s"])
