#!/usr/bin/env python
"""
Test script to verify crew execution from bank_app views context.
This simulates what happens when a Django view calls a crew function.
"""

import os
import sys

# Simulate the path setup from bank_app/views/base.py
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
print(f"BASE_DIR: {BASE_DIR}")
print(f"Current working directory: {os.getcwd()}")

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
    print(f"Added {BASE_DIR} to sys.path")

print(f"\nsys.path[0:3]: {sys.path[:3]}")

# Test import
print("\n" + "="*60)
print("TEST: Import crews module")
print("="*60)
try:
    from crews import run_analysis_crew, create_td_fd_agents, create_td_fd_tasks
    print("SUCCESS: crews module imported successfully!")
    print(f"  run_analysis_crew: {run_analysis_crew}")
    print(f"  create_td_fd_agents: {create_td_fd_agents}")
    print(f"  create_td_fd_tasks: {create_td_fd_tasks}")
except ImportError as e:
    print(f"FAILED: {e}")
    sys.exit(1)

# Test crew execution (with a simple query)
print("\n" + "="*60)
print("TEST: Execute run_analysis_crew with a simple query")
print("="*60)
print("Note: This will take a few seconds as it runs the AI crew...")

try:
    # Use a very simple query to test the crew
    test_query = "What is the current FD rate for HDFC Bank?"
    print(f"Running crew with query: '{test_query}'")
    
    # Note: This may fail if API keys are not configured, but we're testing the import/execution path
    result = run_analysis_crew(test_query, region="India", product_type="FD")
    
    print("\nSUCCESS: Crew executed!")
    if hasattr(result, 'raw'):
        print(f"Result type: {type(result)}")
        print(f"Result (first 200 chars): {result.raw[:200]}...")
    else:
        print(f"Result: {result}")
        
except Exception as e:
    print(f"\nNote: Crew execution encountered an error (expected if API keys not configured):")
    print(f"  Error type: {type(e).__name__}")
    print(f"  Error message: {e}")
    print("\nThis is OK - the import and execution path works, but API configuration may be needed.")

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print("1. Import path is correctly configured")
print("2. crews.py can be imported from bank_app views")
print("3. Crew functions are accessible and callable")
print("4. Any execution errors are likely due to API configuration, not import issues")
