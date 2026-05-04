#!/usr/bin/env python
"""
Test script to verify if bank_app can import from crews.py
This tests various import scenarios to identify the correct approach.
"""

import sys
import os

# Add the Test directory to sys.path to simulate Django's behavior
test_dir = os.path.dirname(os.path.abspath(__file__))
print(f"Test directory: {test_dir}")
print(f"Current working directory: {os.getcwd()}")

# Test 1: Direct import from Test directory
print("\n" + "="*60)
print("TEST 1: Direct import from Test directory")
print("="*60)
try:
    from crews import create_td_fd_agents, create_td_fd_tasks
    print("SUCCESS: Direct import from crews.py works!")
    print(f"  - create_td_fd_agents: {create_td_fd_agents}")
    print(f"  - create_td_fd_tasks: {create_td_fd_tasks}")
except ImportError as e:
    print(f"FAILED: Direct import failed with error: {e}")

# Test 2: Import with Test in path
print("\n" + "="*60)
print("TEST 2: Import with Test directory in path")
print("="*60)
try:
    sys.path.insert(0, test_dir)
    from crews import create_td_fd_agents, create_td_fd_tasks
    print("SUCCESS: Import with Test in path works!")
except ImportError as e:
    print(f"FAILED: Import with Test in path failed: {e}")

# Test 3: Check if bank_app can import crews
print("\n" + "="*60)
print("TEST 3: Simulating bank_app import of crews")
print("="*60)
bank_app_dir = os.path.join(test_dir, "bank_app")
print(f"bank_app directory: {bank_app_dir}")

# Add bank_app to path and try to import crews
sys.path.insert(0, bank_app_dir)
sys.path.insert(0, test_dir)

try:
    # This simulates what happens in views_legacy.py.bak line 90
    from crews import (
        create_td_fd_agents,
        create_td_fd_tasks,
        create_credit_risk_agents,
        create_credit_risk_tasks,
        create_research_agents,
        create_research_tasks,
        run_aml_crew,
        run_router_crew,
        run_loan_creation_crew,
        run_mortgage_analytics_crew,
        generate_fd_template,
        run_visualization_crew,
        run_analysis_crew,
        run_database_crew,
    )
    print("SUCCESS: All crew functions imported successfully from bank_app context!")
    print("\nImported functions:")
    print("  - create_td_fd_agents")
    print("  - create_td_fd_tasks")
    print("  - create_credit_risk_agents")
    print("  - create_credit_risk_tasks")
    print("  - create_research_agents")
    print("  - create_research_tasks")
    print("  - run_aml_crew")
    print("  - run_router_crew")
    print("  - run_loan_creation_crew")
    print("  - run_mortgage_analytics_crew")
    print("  - generate_fd_template")
    print("  - run_visualization_crew")
    print("  - run_analysis_crew")
    print("  - run_database_crew")
except ImportError as e:
    print(f"FAILED: Import from bank_app context failed: {e}")
    print("\nThis is the expected error when running bank_app views without proper path setup.")

# Test 4: Check sys.path after modifications
print("\n" + "="*60)
print("TEST 4: Current sys.path")
print("="*60)
for i, path in enumerate(sys.path):
    print(f"  {i}: {path}")

# Test 5: Verify crewai is available
print("\n" + "="*60)
print("TEST 5: Verify crewai availability")
print("="*60)
try:
    from crewai import Crew, Process, Agent, Task
    print("SUCCESS: crewai is available and importable")
except ImportError as e:
    print(f"FAILED: crewai import failed: {e}")

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print("To make imports work from bank_app views, you need to:")
print("1. Add the Test directory to sys.path before importing crews")
print("2. OR use absolute imports with proper package structure")
print("3. OR configure Django's PYTHONPATH setting")
print("\nRecommended fix: Add this to the top of views files that need crews:")
print("  import sys")
print("  import os")
print("  test_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))")
print("  if test_dir not in sys.path:")
print("      sys.path.insert(0, test_dir)")
print("  from crews import ...")
