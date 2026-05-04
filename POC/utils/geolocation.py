"""
Geolocation utility functions for the Bank POC Django app.

This module provides utilities for detecting user region,
getting country data, and configuring search regions.

Ported from streamlit_ref/helpers.py to match the exact logic.
"""

import json
import logging

import requests

from django.conf import settings

logger = logging.getLogger(__name__)


# Currency symbol mapping for common currencies
CURRENCY_SYMBOLS = {
    'INR': '₹',
    'USD': '$',
    'GBP': '£',
    'CAD': '$',
    'AUD': '$',
    'EUR': '€',
    'JPY': '¥',
    'CNY': '¥',
    'CHF': 'Fr',
    'MXN': '$',
    'BRL': 'R$',
    'KRW': '₩',
    'RUB': '₽',
    'IN': '₹',
    'US': '$',
    'GB': '£',
    'CA': '$',
    'AU': '$',
    'DE': '€',
    'FR': '€',
    'JP': '¥',
    'CN': '¥',
    'BR': 'R$',
    'MX': '$',
    'KR': '₩',
    'RU': '₽',
}

# Flag emoji mapping for country codes
# Each flag is constructed from two regional indicator symbols
FLAG_EMOJI_MAP = {
    'WW': '🌍',  # Worldwide
    'IN': '🇮🇳',
    'US': '🇺🇸',
    'GB': '🇬🇧',
    'CA': '🇨🇦',
    'AU': '🇦🇺',
    'DE': '🇩🇪',
    'FR': '🇫🇷',
    'JP': '🇯🇵',
    'CN': '🇨🇳',
    'BR': '🇧🇷',
    'MX': '🇲🇽',
    'KR': '🇰🇷',
    'RU': '🇷🇺',
    'ES': '🇪🇸',
    'IT': '🇮🇹',
}


def _get_flag_emoji(country_code):
    """Get flag emoji for a country code."""
    return FLAG_EMOJI_MAP.get(country_code, '🌐')

# DuckDuckGo region code mapping
DDG_REGION_MAP = {
    'US': 'us-en',
    'GB': 'uk-en',
    'IN': 'in-en',
    'CA': 'ca-en',
    'AU': 'au-en',
    'DE': 'de-de',
    'FR': 'fr-fr',
    'ES': 'es-es',
    'IT': 'it-it',
    'JP': 'jp-jp',
    'CN': 'cn-zh',
    'BR': 'br-pt',
    'MX': 'mx-es',
    'RU': 'ru-ru',
    'KR': 'kr-ko',
}


def _load_country_data():
    """
    Load country data from tools.config.fetch_country_data() if available,
    otherwise return empty dict.
    """
    try:
        from tools.config import fetch_country_data
        return fetch_country_data()
    except ImportError:
        logger.warning("Could not import fetch_country_data from tools.config")
        return {}
    except Exception as e:
        logger.error(f"Error loading country data: {e}")
        return {}


def _get_currency_symbol(currency_code):
    """Get currency symbol for a currency code."""
    return CURRENCY_SYMBOLS.get(currency_code, '$')


def _get_ddg_region(country_code):
    """Get DuckDuckGo region code for a country."""
    return DDG_REGION_MAP.get(country_code, f"{country_code.lower()}-en")


# Lazy-loaded country data from HDX
_country_data_cache = None


def _get_country_data_raw():
    """Get raw country data from HDX (lazy loaded)."""
    global _country_data_cache
    if _country_data_cache is None:
        _country_data_cache = _load_country_data()
    return _country_data_cache


def get_all_countries():
    """
    Get all available countries from HDX data source.
    Returns a dict keyed by ISO 3166-1 alpha-2 code with full country info.
    Dynamically fetches from fetch_country_data() in tools.config.
    """
    raw_data = _get_country_data_raw()
    
    # Transform HDX data to our format
    countries = {}
    for code, info in raw_data.items():
        currency_code = info.get('currency_code', '')
        countries[code] = {
            'code': code,
            'name': info.get('name', code),
            'currency': _get_currency_symbol(currency_code),
            'currency_code': currency_code,
            'ddg_region': info.get('ddg_region', _get_ddg_region(code)),
            'flag': _get_flag_emoji(code)
        }
    
    # Ensure WW (Worldwide) is always present
    if 'WW' not in countries:
        countries['WW'] = {
            'code': 'WW',
            'name': 'Worldwide',
            'currency': '$',
            'currency_code': 'USD',
            'ddg_region': 'wt-wt',
            'flag': _get_flag_emoji('WW')
        }
    
    return countries


def get_country_display_list():
    """
    Get a list of (code, display_name) tuples for dropdowns.
    Includes flag emoji and currency code in display name.
    """
    countries = get_all_countries()
    result = []
    for code in sorted(countries.keys(), key=lambda x: (
        x == 'WW',  # WW (Worldwide) at the end
        countries[x]['name']
    )):
        info = countries[code]
        flag = info.get('flag', '🌐')
        currency_code = info.get('currency_code', '')
        display = f"{flag} {currency_code}"
        result.append((code, display))
    return result


def get_country_data(country_code):
    """
    Get country data including currency and search region settings.
    
    Args:
        country_code: ISO 3166-1 alpha-2 country code
        
    Returns:
        dict: Country data with currency and region info, or WW fallback
    """
    all_countries = get_all_countries()
    return all_countries.get(country_code, all_countries.get('WW', {
        'code': 'WW',
        'name': 'Worldwide',
        'currency': '$',
        'currency_code': 'USD',
        'ddg_region': 'wt-wt'
    }))


def set_search_region(country_code):
    """
    Configure region settings for searches based on country code.
    Matches streamlit_ref/set_search_region behavior - returns the ddg_region string.

    Args:
        country_code: ISO 3166-1 alpha-2 country code

    Returns:
        str: DuckDuckGo region code (e.g., 'in-en', 'us-en')
    """
    country_data = get_country_data(country_code)
    return country_data.get('ddg_region', f"{country_code.lower()}-en")


def detect_user_region() -> dict:
    """
    Detect user region using ipinfo.io API.
    Ported from streamlit_ref/helpers.py to match exact logic.

    Returns:
        dict: Region data with country_code, country_name, ddg_region,
              currency_symbol, currency_code
    """
    countries = _load_country_data()
    try:
        resp = requests.get("https://ipinfo.io/json", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            cc = data.get("country", "WW").upper()
            info = countries.get(cc, {})
            ddg = set_search_region(cc)
            # Get currency code and map to symbol if not provided or empty
            currency_code = info.get("currency_code", "")
            currency_symbol = info.get("currency_symbol")
            if not currency_symbol and currency_code:
                currency_symbol = _get_currency_symbol(currency_code)
            return {
                "country_code": cc,
                "country_name": info.get("name", cc),
                "ddg_region": ddg,
                "currency_symbol": currency_symbol or "",
                "currency_code": currency_code,
            }
    except Exception:
        pass
    return {
        "country_code": "WW",
        "country_name": "Worldwide",
        "ddg_region": "wt-wt",
        "currency_symbol": "",
        "currency_code": "",
    }


def detect_user_region_with_request(request) -> dict:
    """
    Detect user region using ipinfo.io API (Django request-aware version).
    Includes IP address and city in the response.

    Args:
        request: Django request object

    Returns:
        dict: Region data with country_code, country_name, ddg_region,
              currency_symbol, currency_code, ip_address, city
    """
    countries = _load_country_data()
    
    # Get client IP address
    client_ip = _get_client_ip(request)
    
    fallback_region = {
        "country_code": "WW",
        "country_name": "Worldwide",
        "ddg_region": "wt-wt",
        "currency_symbol": "",
        "currency_code": "",
        "ip_address": client_ip,
        "city": "",
    }

    try:
        resp = requests.get("https://ipinfo.io/json", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            cc = data.get("country", "WW").upper()
            info = countries.get(cc, {})
            ddg = set_search_region(cc)
            # Get currency code and map to symbol if not provided or empty
            currency_code = info.get("currency_code", "")
            currency_symbol = info.get("currency_symbol")
            if not currency_symbol and currency_code:
                currency_symbol = _get_currency_symbol(currency_code)
            return {
                "country_code": cc,
                "country_name": info.get("name", cc),
                "ddg_region": ddg,
                "currency_symbol": currency_symbol or "",
                "currency_code": currency_code,
                "ip_address": client_ip,
                "city": data.get("city", ""),
            }
    except Exception as e:
        logger.warning(f"IP geolocation API failed: {e}. Using fallback region.")
        pass
    
    return fallback_region


def _get_client_ip(request):
    """
    Get the client's IP address from the request.

    Args:
        request: Django request object

    Returns:
        str: Client IP address
    """
    # Check for X-Forwarded-For header (proxy)
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()

    # Check for X-Real-IP header
    x_real_ip = request.META.get('HTTP_X_REAL_IP')
    if x_real_ip:
        return x_real_ip

    # Fall back to REMOTE_ADDR
    return request.META.get('REMOTE_ADDR', '')


def fetch_country_data():
    """
    Fetch country data from tools.config if available.
    Returns dict keyed by country code with country info.
    
    Returns:
        dict: Country data with name, currency_symbol, currency_code
    """
    try:
        from tools.config import fetch_country_data as _fetch_country_data
        return _fetch_country_data()
    except ImportError:
        logger.warning("Could not import fetch_country_data from tools.config")
        return {}
    except Exception as e:
        logger.error(f"Error loading country data: {e}")
        return {}


def format_region_for_display(region_data):
    """
    Format region data for display in templates.
    
    Args:
        region_data: dict with region information
        
    Returns:
        str: Formatted region string
    """
    if not region_data:
        return 'Worldwide'
    
    country_name = region_data.get('country_name', 'Worldwide')
    city = region_data.get('city', '')
    
    if city:
        return f"{city}, {country_name}"
    return country_name


def get_user_region_from_session(request):
    """
    Get the user's region from the Django session.

    Args:
        request: Django request object with session access

    Returns:
        str: Formatted region string (e.g., "City, Country" or "Country")
    """
    # Get region data from session
    region_data = request.session.get('user_region', {})

    if not region_data:
        return 'Worldwide'

    # Format for display using existing helper
    return format_region_for_display(region_data)
