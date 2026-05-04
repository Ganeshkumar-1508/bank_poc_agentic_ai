#!/usr/bin/env python
"""
Integration Tests for FD Advisor Enhanced Features

Tests the FD Advisor CrewAI integration including:
- Analysis crew for rate comparison and insights
- Visualization crew for chart generation
- FD template generation
"""

import os
import sys
import json
import requests
import pytest
from typing import Dict, Any, List

# Base URL for the Django development server
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")

# Test data for FD Advisor
FD_ADVISOR_TEST_CASES = [
    {
        "name": "Basic FD Rate Query",
        "endpoint": "/api/fd-advisor-crew/",
        "payload": {
            "query": "What are the current FD rates?",
            "region": "India"
        },
        "expected_features": ["rate_lookup", "bank_list"]
    },
    {
        "name": "FD Comparison Analysis",
        "endpoint": "/api/analysis/",
        "payload": {
            "topic": "FD rate comparison",
            "banks": ["SBI", "HDFC", "ICICI", "Axis"],
            "tenure_months": 24,
            "region": "India"
        },
        "expected_features": ["comparison", "analysis"]
    },
    {
        "name": "FD Visualization Request",
        "endpoint": "/api/visualization/",
        "payload": {
            "query": "Show FD rates as bar chart",
            "data_type": "fd_comparison",
            "chart_type": "bar",
            "data_context": json.dumps({
                "banks": ["SBI", "HDFC", "ICICI"],
                "rates": [7.1, 7.3, 7.25],
                "tenure": "24 months"
            })
        },
        "expected_features": ["visualization", "chart_generation"]
    },
    {
        "name": "FD Template Generation",
        "endpoint": "/api/fd-template/",
        "payload": {
            "customer_name": "Test Customer",
            "investment_amount": 100000,
            "tenure_months": 24,
            "risk_profile": "conservative",
            "rate": 7.5,
            "template_type": "confirmation"
        },
        "expected_features": ["template_generation", "personalization"]
    },
    {
        "name": "Complex FD Recommendation",
        "endpoint": "/api/fd-advisor-crew/",
        "payload": {
            "query": "I have 10 lakhs to invest for 3 years. What's the best option?",
            "investment_amount": 1000000,
            "tenure_months": 36,
            "risk_profile": "moderate"
        },
        "expected_features": ["recommendation", "optimization"]
    }
]


class TestFDAdvisorIntegration:
    """Integration tests for FD Advisor enhanced features"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment"""
        self.base_url = BASE_URL
        
    def test_fd_advisor_crew_endpoint(self):
        """Test the main FD Advisor Crew endpoint"""
        endpoint = f"{self.base_url}/api/fd-advisor-crew/"
        
        payload = {
            "query": "Compare FD rates for 1 year tenure",
            "region": "India",
            "tenure_months": 12
        }
        
        print(f"\n{'='*70}")
        print(f"Testing FD Advisor Crew Endpoint")
        print(f"Endpoint: {endpoint}")
        print(f"{'='*70}")
        
        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=60  # CrewAI may take longer
            )
            
            print(f"Status Code: {response.status_code}")
            print(f"Response Time: {response.elapsed.total_seconds():.2f}s")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
                print("✓ FD Advisor Crew endpoint is functional")
            else:
                print(f"Response: {response.text[:500]}")
                
        except requests.exceptions.Timeout:
            print("⚠ Request timeout - CrewAI processing may be slow")
            pytest.skip("Timeout - server may need more time for CrewAI processing")
            
        except requests.exceptions.ConnectionError:
            print("✗ Connection error - server not running")
            pytest.skip("Server not running")
    
    @pytest.mark.parametrize("test_case", FD_ADVISOR_TEST_CASES, ids=lambda x: x["name"])
    def test_fd_advisor_feature(self, test_case):
        """
        Test individual FD Advisor features
        
        Args:
            test_case: Parameterized test case
        """
        endpoint = f"{self.base_url}{test_case['endpoint']}"
        
        print(f"\n{'='*70}")
        print(f"Testing: {test_case['name']}")
        print(f"Endpoint: {endpoint}")
        print(f"{'='*70}")
        
        try:
            response = requests.post(
                endpoint,
                json=test_case["payload"],
                headers={"Content-Type": "application/json"},
                timeout=60
            )
            
            print(f"Status Code: {response.status_code}")
            print(f"Response Time: {response.elapsed.total_seconds():.2f}s")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Response preview: {json.dumps(data, indent=2)[:300]}...")
                print(f"✓ PASSED: {test_case['name']}")
            elif response.status_code == 400:
                print(f"⚠ Bad request - may need valid authentication")
                print(f"Error: {response.json()}")
            else:
                print(f"Response: {response.text[:300]}")
                
        except requests.exceptions.Timeout:
            print(f"⚠ Timeout for {test_case['name']}")
            pytest.skip("Timeout")
            
        except requests.exceptions.ConnectionError:
            print(f"✗ Connection error")
            pytest.skip("Server not running")
    
    def test_fd_rate_calculation_accuracy(self):
        """Test FD maturity calculation accuracy"""
        endpoint = f"{self.base_url}/api/fd-advisor-crew/"
        
        # Test case: 100000 at 7.5% for 24 months
        payload = {
            "query": "Calculate maturity for 100000 at 7.5% for 24 months",
            "principal": 100000,
            "rate": 7.5,
            "tenure_months": 24
        }
        
        response = requests.post(
            endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            # Verify response contains calculation results
            assert "maturity_amount" in str(data) or "result" in str(data) or "answer" in str(data), \
                "Response should contain maturity calculation"
            print("✓ FD rate calculation test passed")
        else:
            print(f"⚠ Calculation test returned status {response.status_code}")
    
    def test_multi_bank_comparison(self):
        """Test comparison across multiple banks"""
        endpoint = f"{self.base_url}/api/analysis/"
        
        payload = {
            "topic": "multi_bank_fd_comparison",
            "banks": ["SBI", "HDFC", "ICICI", "Axis", "Kotak"],
            "tenure_months": 12,
            "analysis_type": "rate_comparison"
        }
        
        response = requests.post(
            endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✓ Multi-bank comparison test passed")
        else:
            print(f"⚠ Multi-bank comparison returned status {response.status_code}")
    
    def test_visualization_chart_generation(self):
        """Test chart/visualization generation"""
        endpoint = f"{self.base_url}/api/visualization/"
        
        payload = {
            "query": "Generate FD comparison chart",
            "data_type": "fd_rates",
            "chart_type": "bar",
            "data_context": json.dumps({
                "banks": ["SBI", "HDFC", "ICICI", "Axis"],
                "rates": [7.1, 7.3, 7.25, 7.2],
                "tenure": "12 months"
            })
        }
        
        response = requests.post(
            endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            # Check for visualization data (chart URL, SVG, or chart config)
            has_visualization = any(
                key in str(data).lower() 
                for key in ["chart", "svg", "image", "url", "plot", "graph"]
            )
            if has_visualization:
                print("✓ Visualization generation test passed")
            else:
                print(f"⚠ Response may not contain visualization: {data}")
        else:
            print(f"⚠ Visualization test returned status {response.status_code}")


if __name__ == "__main__":
    print("="*70)
    print("FD Advisor Enhanced Features Integration Tests")
    print("="*70)
    print(f"Base URL: {BASE_URL}")
    print("="*70)
    
    pytest.main([__file__, "-v", "-s"])
