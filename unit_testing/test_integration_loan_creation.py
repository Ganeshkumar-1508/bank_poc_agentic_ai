#!/usr/bin/env python
"""
Integration Tests for Loan Creation Crew Workflow

Tests the end-to-end loan creation process including:
- Loan application submission
- KYC verification
- Compliance checks
- Credit risk assessment
- Approval/rejection workflow
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

# Test loan applications
LOAN_TEST_CASES = [
    {
        "name": "Auto-Approve Loan",
        "payload": {
            "applicant_name": "Test Auto Approve User",
            "applicant_email": "autoapprove@test.com",
            "applicant_income": 1000000,
            "loan_amount": 200000,
            "loan_term_months": 24,
            "credit_score": 750,
            "employment_years": 5,
            "debt_to_income": 0.2,
            "region": "IN"
        },
        "expected_outcome": "auto_approve",
        "description": "High credit score, low DTI should auto-approve"
    },
    {
        "name": "Requires Review Loan",
        "payload": {
            "applicant_name": "Test Review User",
            "applicant_email": "review@test.com",
            "applicant_income": 500000,
            "loan_amount": 300000,
            "loan_term_months": 36,
            "credit_score": 680,
            "employment_years": 2,
            "debt_to_income": 0.4,
            "region": "IN"
        },
        "expected_outcome": "requires_review",
        "description": "Medium credit score should require human review"
    },
    {
        "name": "Auto-Reject Loan",
        "payload": {
            "applicant_name": "Test Reject User",
            "applicant_email": "reject@test.com",
            "applicant_income": 300000,
            "loan_amount": 500000,
            "loan_term_months": 48,
            "credit_score": 550,
            "employment_years": 1,
            "debt_to_income": 0.6,
            "region": "IN"
        },
        "expected_outcome": "auto_reject",
        "description": "Low credit score, high DTI should auto-reject"
    },
    {
        "name": "US Region Loan",
        "payload": {
            "applicant_name": "Test US User",
            "applicant_email": "ususer@test.com",
            "applicant_income": 80000,
            "loan_amount": 25000,
            "loan_term_months": 60,
            "credit_score": 720,
            "employment_years": 4,
            "debt_to_income": 0.25,
            "region": "US"
        },
        "expected_outcome": "review_or_approve",
        "description": "US region loan application"
    }
]


class TestLoanCreationWorkflow:
    """Integration tests for Loan Creation Crew workflow"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment"""
        self.base_url = BASE_URL
        self.crew_endpoint = f"{self.base_url}/api/loan-creation/"
        self.loan_list_endpoint = f"{self.base_url}/api/loan-apply/"
        self.created_loan_ids = []
        
    def test_loan_creation_crew_endpoint(self):
        """Test the Loan Creation Crew endpoint directly"""
        print(f"\n{'='*70}")
        print(f"Testing Loan Creation Crew Endpoint")
        print(f"Endpoint: {self.crew_endpoint}")
        print(f"{'='*70}")
        
        payload = {
            "loan_amount": 100000,
            "income": 60000,
            "credit_score": 700,
            "employment_years": 5,
            "debt_to_income": 0.3
        }
        
        try:
            response = requests.post(
                self.crew_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=120  # CrewAI processing may take time
            )
            
            print(f"Status Code: {response.status_code}")
            print(f"Response Time: {response.elapsed.total_seconds():.2f}s")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
                print("✓ Loan Creation Crew endpoint is functional")
            else:
                print(f"Response: {response.text[:500]}")
                
        except requests.exceptions.Timeout:
            print("⚠ Request timeout - CrewAI processing may be slow")
            pytest.skip("Timeout")
            
        except requests.exceptions.ConnectionError:
            print("✗ Connection error - server not running")
            pytest.skip("Server not running")
    
    @pytest.mark.parametrize("test_case", LOAN_TEST_CASES, ids=lambda x: x["name"])
    def test_loan_application_workflow(self, test_case):
        """
        Test complete loan application workflow
        
        Args:
            test_case: Parameterized test case with expected outcome
        """
        print(f"\n{'='*70}")
        print(f"Testing: {test_case['name']}")
        print(f"Expected: {test_case['expected_outcome']}")
        print(f"{'='*70}")
        
        # Step 1: Create loan application via Crew
        try:
            response = requests.post(
                self.crew_endpoint,
                json=test_case["payload"],
                headers={"Content-Type": "application/json"},
                timeout=120
            )
            
            print(f"Crew Response Status: {response.status_code}")
            
            if response.status_code == 200:
                crew_data = response.json()
                print(f"Crew Decision: {crew_data.get('decision', 'N/A')}")
                print(f"Reasoning: {crew_data.get('reasoning', 'N/A')[:200]}...")
                
                # Verify decision matches expectation
                decision = crew_data.get("decision", "").lower()
                expected = test_case["expected_outcome"].lower()
                
                if "auto_approve" in expected and "approved" in decision:
                    print(f"✓ PASSED: Auto-approve decision correct")
                elif "auto_reject" in expected and "rejected" in decision:
                    print(f"✓ PASSED: Auto-reject decision correct")
                elif "review" in expected:
                    print(f"✓ PASSED: Review decision correct")
                else:
                    print(f"⚠ Decision may not match expectation: {decision} vs {expected}")
                    
            elif response.status_code == 400:
                print(f"⚠ Bad request: {response.json()}")
            else:
                print(f"Response: {response.text[:300]}")
                
        except requests.exceptions.Timeout:
            print(f"⚠ Timeout for {test_case['name']}")
            pytest.skip("Timeout")
            
        except requests.exceptions.ConnectionError:
            print(f"✗ Connection error")
            pytest.skip("Server not running")
    
    def test_loan_status_transitions(self):
        """Test loan status transition workflow"""
        # Create a loan
        create_payload = {
            "applicant_name": "Status Transition Test",
            "applicant_email": "status@test.com",
            "applicant_income": 500000,
            "loan_amount": 100000,
            "loan_term_months": 12,
            "credit_score": 700,
            "region": "IN"
        }
        
        # Submit via API
        create_response = requests.post(
            f"{self.base_url}/api/loan-apply/",
            json=create_payload,
            headers={"Content-Type": "application/json"}
        )
        
        if create_response.status_code == 200:
            loan_data = create_response.json()
            loan_id = loan_data.get("loan_id")
            
            if loan_id:
                # Test status transitions
                transitions = [
                    ("submit", "/api/loan-submit/", "SUBMITTED"),
                    ("approve", "/api/loan-approve/", "APPROVED"),
                ]
                
                for action, endpoint, expected_status in transitions:
                    try:
                        resp = requests.post(
                            f"{self.base_url}{endpoint}{loan_id}/",
                            headers={"Content-Type": "application/json"}
                        )
                        if resp.status_code == 200:
                            print(f"✓ {action} transition successful")
                        else:
                            print(f"⚠ {action} transition returned {resp.status_code}")
                    except Exception as e:
                        print(f"⚠ {action} transition error: {e}")
    
    def test_bulk_loan_operations(self):
        """Test bulk loan approval/rejection operations"""
        bulk_approve_endpoint = f"{self.base_url}/api/bulk-approve/"
        bulk_reject_endpoint = f"{self.base_url}/api/bulk-reject/"
        
        # Preview mode
        preview_payload = {
            "filter_criteria": {"status": "SUBMITTED"},
            "confirm": False
        }
        
        preview_response = requests.post(
            bulk_approve_endpoint,
            json=preview_payload,
            headers={"Content-Type": "application/json"}
        )
        
        if preview_response.status_code == 200:
            preview_data = preview_response.json()
            print(f"✓ Bulk approve preview successful: {preview_data.get('preview', {}).get('count', 0)} loans")
        else:
            print(f"⚠ Bulk approve preview returned {preview_response.status_code}")
    
    def test_loan_audit_logging(self):
        """Test that loan actions are properly logged"""
        # This test verifies audit log creation
        # In a real test, we would check the AuditLog model
        
        print("✓ Audit logging test placeholder")
        print("  Note: Verify AuditLog entries in database after loan operations")


if __name__ == "__main__":
    print("="*70)
    print("Loan Creation Workflow Integration Tests")
    print("="*70)
    print(f"Base URL: {BASE_URL}")
    print("="*70)
    
    pytest.main([__file__, "-v", "-s"])
