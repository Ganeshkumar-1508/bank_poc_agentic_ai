#!/usr/bin/env python
"""
Test Runner Script for All Integration Tests

This script runs all integration tests and generates a summary report.
"""

import os
import sys
import subprocess
import json
from datetime import datetime

# Test files to run
TEST_FILES = [
    "test_integration_smart_assistant.py",
    "test_integration_fd_advisor.py",
    "test_integration_loan_creation.py",
    "test_integration_fd_creation.py",
    "test_integration_email_campaigns.py",
    "test_integration_database_query.py",
]

def run_tests():
    """Run all integration tests and collect results."""
    
    print("="*70)
    print("Bank POC Agentic AI - Integration Test Suite")
    print("="*70)
    print(f"Started at: {datetime.now().isoformat()}")
    print(f"Base URL: {os.environ.get('TEST_BASE_URL', 'http://localhost:8000')}")
    print("="*70)
    print()
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "base_url": os.environ.get("TEST_BASE_URL", "http://localhost:8000"),
        "tests": [],
        "summary": {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0
        }
    }
    
    for test_file in TEST_FILES:
        print(f"\n{'='*70}")
        print(f"Running: {test_file}")
        print(f"{'='*70}")
        
        # Change to the unit_testing directory before running pytest
        test_dir = os.path.dirname(os.path.abspath(__file__))
        cmd = [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"]
    
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes per test file
                cwd=test_dir  # Run from the unit_testing directory
            )
            
            test_result = {
                "file": test_file,
                "returncode": result.returncode,
                "stdout": result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
                "stderr": result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr,
            }
            
            # Parse summary from output
            if "passed" in result.stdout:
                test_result["status"] = "passed"
                results["summary"]["passed"] += 1
            elif "failed" in result.stdout:
                test_result["status"] = "failed"
                results["summary"]["failed"] += 1
            else:
                test_result["status"] = "unknown"
            
            results["tests"].append(test_result)
            results["summary"]["total"] += 1
            
            print(result.stdout)
            if result.stderr:
                print(f"STDERR: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            print(f"TIMEOUT: {test_file} exceeded 5 minutes")
            results["tests"].append({
                "file": test_file,
                "status": "timeout",
                "error": "Test exceeded 5 minutes"
            })
            results["summary"]["total"] += 1
            results["summary"]["failed"] += 1
            
        except Exception as e:
            print(f"ERROR running {test_file}: {e}")
            results["tests"].append({
                "file": test_file,
                "status": "error",
                "error": str(e)
            })
            results["summary"]["total"] += 1
            results["summary"]["failed"] += 1
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Total Tests: {results['summary']['total']}")
    print(f"Passed: {results['summary']['passed']}")
    print(f"Failed: {results['summary']['failed']}")
    print(f"Skipped: {results['summary']['skipped']}")
    print("="*70)
    
    # Save results to file
    results_file = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nDetailed results saved to: {results_file}")
    
    return results["summary"]["failed"] == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
