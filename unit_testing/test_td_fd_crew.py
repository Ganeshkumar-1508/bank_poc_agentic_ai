"""
test_td_fd_crew.py
==================
Test script for TD/FD Agent functionality.

This script demonstrates:
1. TD/FD provider selection based on user intent
2. TD/FD creation in the database
3. Email notification sending

Run: python test_td_fd_crew.py
"""

import os
import sys
from pathlib import Path

# Add the Test directory to the path
sys.path.insert(0, str(Path(__file__).parent / "Test"))

from crews import run_td_fd_creation


def test_td_fd_crew():
    """Test the TD/FD creation function with sample data."""

    print("=" * 60)
    print("TD/FD Agent Test")
    print("=" * 60)

    # Test Case 1: Create FD with best rate intent
    print("\n[Test 1] Creating FD with 'best rate' intent...")
    user_query_1 = """
    I want to create a Fixed Deposit of Rs. 5,00,000 for 12 months.
    I want the bank with the BEST INTEREST RATE.
    My email is user@example.com
    """

    try:
        result = run_td_fd_creation(
            user_query=user_query_1, user_email="user@example.com", user_id=1
        )
        print("\n[Result 1]")
        print(result.raw if hasattr(result, "raw") else str(result))
    except Exception as e:
        print(f"\n[Error 1] {e}")

    # Test Case 2: Create FD with safest bank intent
    print("\n" + "=" * 60)
    print("\n[Test 2] Creating FD with 'safest bank' intent...")
    user_query_2 = """
    I want to create a Fixed Deposit of Rs. 10,00,000 for 24 months.
    I want the SAFEST BANK with government backing.
    My email is user@example.com
    """

    try:
        result = run_td_fd_creation(
            user_query=user_query_2, user_email="user@example.com", user_id=1
        )
        print("\n[Result 2]")
        print(result.raw if hasattr(result, "raw") else str(result))
    except Exception as e:
        print(f"\n[Error 2] {e}")

    # Test Case 3: Create RD (Recurring Deposit)
    print("\n" + "=" * 60)
    print("\n[Test 3] Creating RD with 'best maturity' intent...")
    user_query_3 = """
    I want to create a Recurring Deposit of Rs. 10,000 per month for 12 months.
    I want the HIGHEST MATURITY AMOUNT.
    My email is user@example.com
    """

    try:
        result = run_td_fd_creation(
            user_query=user_query_3, user_email="user@example.com", user_id=1
        )
        print("\n[Result 3]")
        print(result.raw if hasattr(result, "raw") else str(result))
    except Exception as e:
        print(f"\n[Error 3] {e}")

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    test_td_fd_crew()
