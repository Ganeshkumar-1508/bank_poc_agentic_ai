#!/usr/bin/env python3
"""
Test script to verify Neo4j connectivity after fixes.
Run this script to check if Neo4j connection is working.
"""

import sys
import os
import logging

# Set up logging to see detailed output
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Add the Test directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_neo4j_connection_test():
    """Test Neo4j connection using the fixed config module."""
    print("=" * 60)
    print("Neo4j Connection Test")
    print("=" * 60)

    try:
        # Import the test function from config directly
        # Avoid importing through tools package to prevent dependency issues
        import importlib.util

        config_path = os.path.join(os.path.dirname(__file__), "tools", "config.py")
        spec = importlib.util.spec_from_file_location("config", config_path)
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)

        test_func = config.test_neo4j_connection
        NEO4J_URI = config.NEO4J_URI
        NEO4J_USER = config.NEO4J_USER
        NEO4J_PASSWORD = config.NEO4J_PASSWORD

        print(f"\nConfiguration:")
        print(f"  NEO4J_URI: {NEO4J_URI}")
        print(f"  NEO4J_USER: {NEO4J_USER}")
        print(
            f"  NEO4J_PASSWORD: {'*' * len(NEO4J_PASSWORD) if NEO4J_PASSWORD else '(not set)'}"
        )

        # Run the connection test
        result = test_func()

        print(f"\nConnection Test Result:")
        print(f"  Success: {result['success']}")
        print(f"  Message: {result['message']}")
        print(f"  Driver Available: {result['driver_available']}")
        print(f"  Graph Available: {result['graph_available']}")

        if result["success"]:
            print("\n[OK] Neo4j connection is working!")
            return True
        else:
            print("\n[FAIL] Neo4j connection failed. Please check:")
            print("  1. Neo4j database is running on the configured URI")
            print("  2. Credentials in .env file are correct")
            print("  3. Network connectivity to the Neo4j server")
            return False

    except ImportError as e:
        print(f"\n[FAIL] Import error: {e}")
        print("Make sure you're running this from the Test/ directory")
        return False
    except Exception as e:
        print(f"\n[FAIL] Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_neo4j_connection_test()
    sys.exit(0 if success else 1)
