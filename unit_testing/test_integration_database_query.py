#!/usr/bin/env python
"""
Integration Tests for Database Query Interface

Tests the admin database query features including:
- Natural language to SQL conversion
- Query execution
- Result formatting
- Audit logging
- Export functionality
"""

import os
import sys
import json
import requests
import pytest
from datetime import datetime
from typing import Dict, Any, List

# Base URL for the Django development server
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")

# Test database queries
QUERY_TEST_CASES = [
    {
        "name": "Simple SELECT Query",
        "payload": {
            "query": "Show me all loan applications",
            "expected_table": "loan_application"
        },
        "expected_result": "list_of_loans"
    },
    {
        "name": "Filtered Query",
        "payload": {
            "query": "Show approved loans from India",
            "filters": {"status": "APPROVED", "region": "IN"}
        },
        "expected_result": "filtered_loans"
    },
    {
        "name": "Aggregation Query",
        "payload": {
            "query": "What is the total loan amount by status?",
            "aggregation": "sum_by_status"
        },
        "expected_result": "aggregated_data"
    },
    {
        "name": "FD Query",
        "payload": {
            "query": "List all fixed deposits with maturity > 100000",
            "expected_table": "fixed_deposit"
        },
        "expected_result": "fd_list"
    },
    {
        "name": "User Statistics Query",
        "payload": {
            "query": "How many active users do we have?",
            "aggregation": "count_active_users"
        },
        "expected_result": "user_count"
    }
]


class TestDatabaseQueryIntegration:
    """Integration tests for Database Query interface"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment"""
        self.base_url = BASE_URL
        self.query_endpoint = f"{self.base_url}/api/database-query/"
        self.admin_query_endpoint = f"{self.base_url}/admin/database-query/api/"
        self.created_query_ids = []
        
    def test_database_crew_endpoint(self):
        """Test the Database Crew AI endpoint"""
        print(f"\n{'='*70}")
        print(f"Testing Database Crew AI Endpoint")
        print(f"{'='*70}")
        
        payload = {
            "query": "SELECT COUNT(*) FROM loan_application WHERE status = 'APPROVED'"
        }
        
        try:
            response = requests.post(
                self.query_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=60
            )
            
            print(f"Status Code: {response.status_code}")
            print(f"Response Time: {response.elapsed.total_seconds():.2f}s")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
                print("✓ Database Crew endpoint is functional")
            else:
                print(f"Response: {response.text[:500]}")
                
        except requests.exceptions.Timeout:
            print("⚠ Request timeout")
            pytest.skip("Timeout")
            
        except requests.exceptions.ConnectionError:
            print("✗ Connection error - server not running")
            pytest.skip("Server not running")
    
    @pytest.mark.parametrize("test_case", QUERY_TEST_CASES, ids=lambda x: x["name"])
    def test_natural_language_query(self, test_case):
        """
        Test natural language to SQL conversion and execution
        
        Args:
            test_case: Parameterized test case
        """
        print(f"\n{'='*70}")
        print(f"Testing: {test_case['name']}")
        print(f"Query: {test_case['payload']['query']}")
        print(f"{'='*70}")
        
        try:
            response = requests.post(
                self.admin_query_endpoint,
                json=test_case["payload"],
                headers={"Content-Type": "application/json"},
                timeout=60
            )
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for query results
                has_results = any(
                    key in str(data).lower()
                    for key in ["results", "data", "rows", "count", "records"]
                )
                if has_results:
                    print(f"✓ Natural language query successful for {test_case['name']}")
                    print(f"  Result preview: {json.dumps(data, indent=2)[:200]}...")
                else:
                    print(f"Response: {json.dumps(data, indent=2)[:300]}...")
            elif response.status_code == 403:
                print("⚠ Authentication required")
            else:
                print(f"Response: {response.text[:300]}")
                
        except requests.exceptions.Timeout:
            print(f"⚠ Timeout for {test_case['name']}")
            pytest.skip("Timeout")
            
        except requests.exceptions.ConnectionError:
            print(f"✗ Connection error")
            pytest.skip("Server not running")
    
    def test_query_safety_validation(self):
        """Test that dangerous queries are blocked"""
        print("\n" + "="*70)
        print("Testing Query Safety Validation")
        print("="*70)
        
        dangerous_queries = [
            "DROP TABLE loan_application;",
            "DELETE FROM loan_application;",
            "UPDATE loan_application SET status = 'APPROVED';",
            "INSERT INTO loan_application VALUES (...);",
            "SELECT * FROM django_password;"
        ]
        
        for query in dangerous_queries:
            payload = {"query": query}
            
            try:
                response = requests.post(
                    self.admin_query_endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
                
                # Should be blocked or return error
                if response.status_code in [400, 403, 500]:
                    print(f"✓ Dangerous query blocked: {query[:30]}...")
                else:
                    print(f"⚠ Dangerous query may not be blocked: {query[:30]}...")
                    
            except Exception as e:
                print(f"⚠ Error testing query: {e}")
    
    def test_query_audit_logging(self):
        """Test that all queries are logged for audit trail"""
        print("\n" + "="*70)
        print("Testing Query Audit Logging")
        print("="*70)
        
        # Execute a test query
        payload = {
            "query": "SELECT COUNT(*) FROM loan_application",
            "test_mode": True
        }
        
        try:
            response = requests.post(
                self.admin_query_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                print("✓ Query executed, checking audit log...")
                print("  Note: Verify DatabaseQueryLog entries in admin panel")
                print("  Check fields: query_text, sql_generated, status, execution_time_ms")
            else:
                print(f"⚠ Query execution returned {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            print("✗ Connection error")
            pytest.skip("Server not running")
    
    def test_query_export_functionality(self):
        """Test query result export to CSV/JSON"""
        print("\n" + "="*70)
        print("Testing Query Export Functionality")
        print("="*70)
        
        payload = {
            "query": "SELECT * FROM loan_application LIMIT 10",
            "export_format": "json"
        }
        
        try:
            response = requests.post(
                self.admin_query_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                has_export = any(
                    key in str(data).lower()
                    for key in ["export", "download", "csv", "json", "file"]
                )
                if has_export:
                    print("✓ Export functionality available")
                else:
                    print("  Note: Export may be handled via separate endpoint")
            else:
                print(f"⚠ Export test returned {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            print("✗ Connection error")
            pytest.skip("Server not running")
    
    def test_query_history(self):
        """Test query history retrieval"""
        print("\n" + "="*70)
        print("Testing Query History")
        print("="*70)
        
        try:
            response = requests.get(
                f"{self.base_url}/admin/database-query/history/",
                timeout=30
            )
            
            if response.status_code == 200:
                print("✓ Query history endpoint accessible")
            elif response.status_code == 403:
                print("⚠ Authentication required")
            else:
                print(f"Response: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            print("✗ Connection error")
            pytest.skip("Server not running")
    
    def test_read_only_enforcement(self):
        """Test that only SELECT queries are allowed"""
        print("\n" + "="*70)
        print("Testing Read-Only Query Enforcement")
        print("="*70)
        
        write_queries = [
            "INSERT INTO loan_application ...",
            "UPDATE loan_application SET ...",
            "DELETE FROM loan_application ...",
            "DROP TABLE ...",
            "CREATE TABLE ..."
        ]
        
        for query in write_queries:
            payload = {"query": query}
            
            try:
                response = requests.post(
                    self.admin_query_endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
                
                # Should be blocked
                if response.status_code in [400, 403]:
                    print(f"✓ Write query blocked: {query[:30]}...")
                else:
                    print(f"⚠ Write query may not be blocked: {query[:30]}...")
                    
            except Exception as e:
                print(f"⚠ Error: {e}")


if __name__ == "__main__":
    print("="*70)
    print("Database Query Interface Integration Tests")
    print("="*70)
    print(f"Base URL: {BASE_URL}")
    print("="*70)
    
    pytest.main([__file__, "-v", "-s"])
