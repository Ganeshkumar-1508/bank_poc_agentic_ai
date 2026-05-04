#!/usr/bin/env python
"""Test script to verify fetch_country_data() implementation with hdx-python-country."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Suppress warnings
import warnings
warnings.filterwarnings('ignore')

from tools.config import fetch_country_data

def main():
    print("Testing fetch_country_data() implementation with hdx-python-country...")
    print("=" * 70)

    data = fetch_country_data()
    print(f"Total countries returned: {len(data)}")
    print()

    # Check sample countries
    sample_codes = ['US', 'IN', 'GB', 'DE', 'WW']
    print("Sample country entries:")
    for code in sample_codes:
        if code in data:
            entry = data[code]
            print(f"  {code}:")
            print(f"    name: {entry.get('name', 'N/A')}")
            print(f"    official_name: {entry.get('official_name', 'N/A')}")
            print(f"    alpha_3: {entry.get('alpha_3', 'N/A')}")
            print(f"    currency_code: {entry.get('currency_code', 'N/A')}")
            print(f"    currency_symbol: {entry.get('currency_symbol', 'N/A') or '(not available)'}")
            print(f"    ddg_region: {entry.get('ddg_region', 'N/A')}")
            print()
        else:
            print(f"  {code}: NOT FOUND")

    # Verify all required fields exist
    print("Verifying required fields in all entries...")
    required_fields = ['name', 'official_name', 'alpha_3', 'currency_code', 'currency_symbol', 'ddg_region']
    missing_fields = []
    for code, entry in data.items():
        for field in required_fields:
            if field not in entry:
                missing_fields.append((code, field))

    if missing_fields:
        print(f"  WARNING: Missing fields found: {missing_fields[:5]}...")
    else:
        print("  All entries have all required fields!")

    # Count countries with currency info
    countries_with_currency = sum(1 for entry in data.values() if entry.get('currency_code'))
    print(f"\nCountries with currency information: {countries_with_currency}")

    # Show some countries with currency codes
    print("\nSample countries with currency codes:")
    count = 0
    for code, entry in sorted(data.items())[:10]:
        if entry.get('currency_code'):
            print(f"  {code}: {entry['name']} - {entry['currency_code']}")
            count += 1
            if count >= 10:
                break

    print("\n" + "=" * 70)
    print("Test completed successfully!")

if __name__ == '__main__':
    main()
