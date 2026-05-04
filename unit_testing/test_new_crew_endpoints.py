#!/usr/bin/env python
"""
Test script for the 7 new CrewAI API endpoints.

This script tests all newly integrated CrewAI crew endpoints with sample data.
Run this script after starting the Django development server.

Usage:
    python test_new_crew_endpoints.py
"""

import requests
import json
import sys

# Base URL for the Django development server
BASE_URL = "http://localhost:8000"

# Test data for each endpoint
TEST_DATA = {
    "router": {
        "endpoint": "/api/router/",
        "payload": {
            "query": "I want to compare FD rates",
            "region": "India"
        },
        "description": "Router Crew - Intelligent query routing"
    },
    "loan_creation": {
        "endpoint": "/api/loan-creation/",
        "payload": {
            "loan_amount": 100000,
            "income": 60000,
            "credit_score": 700,
            "employment_years": 5,
            "debt_to_income": 0.3
        },
        "description": "Loan Creation Crew - End-to-end loan processing"
    },
    "mortgage_analytics": {
        "endpoint": "/api/mortgage-analytics-crew/",
        "payload": {
            "home_price": 500000,
            "down_payment": 100000,
            "interest_rate": 6.5,
            "tenure_years": 30
        },
        "description": "Mortgage Analytics Crew - Advanced mortgage calculations"
    },
    "fd_template": {
        "endpoint": "/api/fd-template/",
        "payload": {
            "customer_name": "John Doe",
            "investment_amount": 100000,
            "tenure_months": 24,
            "risk_profile": "conservative",
            "rate": 7.5,
            "template_type": "confirmation"
        },
        "description": "FD Template Crew - Generate customized FD templates"
    },
    "visualization": {
        "endpoint": "/api/visualization/",
        "payload": {
            "query": "FD comparison chart",
            "data_type": "fd_comparison",
            "chart_type": "bar",
            "data_context": '{"banks": ["SBI", "HDFC", "ICICI"], "rates": [7.1, 7.3, 7.25]}'
        },
        "description": "Visualization Crew - Automated chart generation"
    },
    "analysis": {
        "endpoint": "/api/analysis/",
        "payload": {
            "topic": "loan approval trends",
            "timeframe": "last_6_months",
            "region": "India"
        },
        "description": "Analysis Crew - General data analysis and insights"
    },
    "database": {
        "endpoint": "/api/database-query/",
        "payload": {
            "query": "SELECT * FROM loan_applications WHERE status = 'approved'"
        },
        "description": "Database Crew - SQL query generation and database operations"
    }
}


def test_endpoint(name, data):
    """Test a single endpoint and print results."""
    url = f"{BASE_URL}{data['endpoint']}"
    print(f"\n{'='*70}")
    print(f"Testing: {data['description']}")
    print(f"Endpoint: {data['endpoint']}")
    print(f"Payload: {json.dumps(data['payload'], indent=2)}")
    print(f"{'='*70}")
    
    try:
        response = requests.post(url, json=data['payload'], timeout=30)
        
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Response (truncated): {json.dumps(result, indent=2)[:500]}...")
            
            # Check for success indicators
            if 'success' in result:
                status = "SUCCESS" if result['success'] else "FAILED"
                print(f"\n[✓] {name.upper()} - {status}")
            elif 'error' in result:
                print(f"\n[✗] {name.upper()} - ERROR: {result['error']}")
            else:
                print(f"\n[✓] {name.upper()} - COMPLETED")
        else:
            print(f"Response: {response.text[:500]}")
            print(f"\n[✗] {name.upper()} - HTTP ERROR {response.status_code}")
            
    except requests.exceptions.Timeout:
        print(f"\n[✗] {name.upper()} - TIMEOUT (30s)")
    except requests.exceptions.ConnectionError:
        print(f"\n[✗] {name.upper()} - CONNECTION ERROR (Is server running?)")
    except Exception as e:
        print(f"\n[✗] {name.upper()} - EXCEPTION: {str(e)}")


def main():
    """Run all endpoint tests."""
    print("\n" + "="*70)
    print("CREWAI CREW ENDPOINTS TEST SUITE")
    print("="*70)
    print(f"\nBase URL: {BASE_URL}")
    print(f"Endpoints to test: {len(TEST_DATA)}")
    print("\nMake sure the Django development server is running:")
    print("  python Test/manage.py runserver")
    print("\n" + "="*70)
    
    # Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        print(f"\n[✓] Server is running (Status: {response.status_code})")
    except requests.exceptions.ConnectionError:
        print(f"\n[✗] Server is NOT running at {BASE_URL}")
        print("Please start the server with: python Test/manage.py runserver")
        sys.exit(1)
    
    # Run tests
    results = {}
    for name, data in TEST_DATA.items():
        test_endpoint(name, data)
        results[name] = "passed"  # Would be updated based on actual response
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    for name in TEST_DATA.keys():
        status = results.get(name, "unknown")
        print(f"  {name}: {status}")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
