#!/usr/bin/env python
"""
Test script to verify the correct path setup for importing crews.py from bank_app views.
This tests the actual path calculation used in views_legacy.py.bak vs the correct one.
"""

import os
import sys

# Simulate the path from bank_app/views_legacy.py.bak
script_path = "Test/bank_app/views_legacy.py.bak"

print("="*70)
print("PATH CALCULATION TEST")
print("="*70)
print(f"Script location: {script_path}")
print(f"Current working directory: {os.getcwd()}")
print()

# Current (incorrect) approach - 3 levels up
print("CURRENT APPROACH (3 levels up - INCORRECT):")
print("-"*50)
BASE_DIR_3 = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(script_path))))
print(f"BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))")
print(f"Result: {os.path.abspath(BASE_DIR_3)}")
print(f"crews.py exists at: {os.path.join(os.path.abspath(BASE_DIR_3), 'crews.py')}")
print(f"crews.py found? {os.path.exists(os.path.join(os.path.abspath(BASE_DIR_3), 'crews.py'))}")
print()

# Correct approach - 2 levels up
print("CORRECT APPROACH (2 levels up):")
print("-"*50)
BASE_DIR_2 = os.path.dirname(os.path.dirname(os.path.abspath(script_path)))
print(f"BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))")
print(f"Result: {os.path.abspath(BASE_DIR_2)}")
print(f"crews.py exists at: {os.path.join(os.path.abspath(BASE_DIR_2), 'crews.py')}")
print(f"crews.py found? {os.path.exists(os.path.join(os.path.abspath(BASE_DIR_2), 'crews.py'))}")
print()

# Test import with correct path
print("TESTING IMPORT WITH CORRECT PATH:")
print("-"*50)
sys.path.insert(0, os.path.abspath(BASE_DIR_2))
print(f"Added to sys.path: {os.path.abspath(BASE_DIR_2)}")

try:
    from crews import create_td_fd_agents, create_td_fd_tasks
    print("SUCCESS: crews.py imported successfully!")
    print(f"  create_td_fd_agents: {create_td_fd_agents}")
    print(f"  create_td_fd_tasks: {create_td_fd_tasks}")
except ImportError as e:
    print(f"FAILED: {e}")

print()
print("="*70)
print("RECOMMENDATION")
print("="*70)
print("Change line 56 in Test/bank_app/views_legacy.py.bak from:")
print("  BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))")
print("To:")
print("  BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))")
print()
print("This will correctly point to the Test/ directory where crews.py is located.")
