#!/usr/bin/env python
"""Standalone test for fetch_country_data() using hdx-python-country."""

import sys
import warnings
from functools import lru_cache
from typing import Dict

warnings.filterwarnings('ignore')

# Copy of the fetch_country_data function for testing
@lru_cache(maxsize=None)
def fetch_country_data() -> Dict[str, Dict]:
    """
    Fetches complete country data using hdx-python-country library.
    Returns a dict keyed by ISO 3166-1 alpha-2 code.
    """
    country_data = {}

    ddg_region_map = {
        'US': 'us-en', 'GB': 'uk-en', 'IN': 'in-en', 'CA': 'ca-en',
        'AU': 'au-en', 'DE': 'de-de', 'FR': 'fr-fr', 'ES': 'es-es',
        'IT': 'it-it', 'JP': 'jp-jp', 'CN': 'cn-zh', 'BR': 'br-pt',
        'MX': 'mx-es', 'RU': 'ru-ru', 'KR': 'kr-ko',
    }

    try:
        from hdx.location.country import Country
        hdx_data = Country().countriesdata()
        countries = hdx_data.get('countries', {})

        for iso3, country_info in countries.items():
            alpha_2 = country_info.get('ISO 3166-1 Alpha 2-Codes', '')
            if not alpha_2:
                continue

            name = country_info.get('English Short', '')
            official_name = country_info.get('English Formal', name)
            currency_code = country_info.get('Currency', '') or ''
            currency_symbol = ''
            ddg_region = ddg_region_map.get(alpha_2, f"{alpha_2.lower()}-en")

            country_data[alpha_2] = {
                "name": name,
                "official_name": official_name,
                "alpha_3": iso3,
                "currency_code": currency_code,
                "currency_symbol": currency_symbol,
                "ddg_region": ddg_region,
            }
    except Exception as e:
        print(f"Error: {e}")

    country_data["WW"] = {
        "name": "Worldwide",
        "official_name": "Worldwide",
        "alpha_3": "",
        "currency_code": "",
        "currency_symbol": "",
        "ddg_region": "wt-wt",
    }

    return country_data


def main():
    print("Testing fetch_country_data() with hdx-python-country...")
    print("=" * 70)

    data = fetch_country_data()
    print(f"Total countries returned: {len(data)}")
    print()

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

    countries_with_currency = sum(1 for entry in data.values() if entry.get('currency_code'))
    print(f"Countries with currency information: {countries_with_currency}")

    print("\nSample countries with currency codes:")
    count = 0
    for code, entry in sorted(data.items())[:15]:
        if entry.get('currency_code'):
            print(f"  {code}: {entry['name']} - {entry['currency_code']}")
            count += 1

    print("\n" + "=" * 70)
    print("Test completed!")


if __name__ == '__main__':
    main()
