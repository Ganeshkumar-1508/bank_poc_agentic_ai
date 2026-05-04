"""
Countries-States-Cities API endpoints.
Provides geographic data for country, state, and city selection dropdowns.
"""

import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .base import (
    logger,
    COUNTRYSATECITY_AVAILABLE,
    get_countries as base_get_countries,
    get_states_of_country as base_get_states_of_country,
    get_cities_of_state as base_get_cities_of_state,
)

# Try to import from countrystatecity package
try:
    from countrystatecity_countries import (
        get_countries as pkg_get_countries,
        get_states_of_country as pkg_get_states_of_country,
        get_cities_of_state as pkg_get_cities_of_state,
    )
    COUNTRYSATECITY_AVAILABLE = True
except ImportError:
    COUNTRYSATECITY_AVAILABLE = False
    pkg_get_countries = None
    pkg_get_states_of_country = None
    pkg_get_cities_of_state = None

# Currency symbol mapping for common currencies
CURRENCY_SYMBOLS = {
    'INR': '₹', 'USD': '$', 'GBP': '£', 'CAD': '$', 'AUD': '$',
    'EUR': '€', 'JPY': '¥', 'CNY': '¥', 'CHF': 'Fr', 'MXN': '$',
    'BRL': 'R$', 'KRW': '₩', 'RUB': '₽',
    # Country code to currency symbol fallback
    'IN': '₹', 'US': '$', 'GB': '£', 'CA': '$', 'AU': '$',
    'DE': '€', 'FR': '€', 'JP': '¥', 'CN': '¥', 'BR': 'R$',
    'MX': '$', 'KR': '₩', 'RU': '₽',
}


def get_countries():
    """Get countries - prefer package if available, fallback to base."""
    if COUNTRYSATECITY_AVAILABLE and pkg_get_countries:
        return pkg_get_countries()
    return base_get_countries()


def get_states_of_country(country_code):
    """Get states for a country - prefer package if available, fallback to base."""
    if COUNTRYSATECITY_AVAILABLE and pkg_get_states_of_country:
        return pkg_get_states_of_country(country_code)
    return base_get_states_of_country(country_code)


def get_cities_of_state(country_code, state_code):
    """Get cities for a state - prefer package if available, fallback to base."""
    if COUNTRYSATECITY_AVAILABLE and pkg_get_cities_of_state:
        return pkg_get_cities_of_state(country_code, state_code)
    return base_get_cities_of_state(country_code, state_code)

logger = logging.getLogger(__name__)


# =============================================================================
# COUNTRIES-STATES-CITIES API ENDPOINTS
# =============================================================================

@csrf_exempt
def get_countries_api(request):
    """
    API endpoint to get all countries.
    Returns JSON with country code, name, emoji, and currency.
    
    GET /api/countries-states/countries/
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    if not COUNTRYSATECITY_AVAILABLE:
        return JsonResponse({'error': 'countrystatecity-countries package not installed'}, status=503)
    
    try:
        countries = get_countries()
        countries_data = []
        for c in countries:
            iso2 = c.iso2
            # Try to get currency code from the country object
            currency_code = getattr(c, 'currency_code', None) or getattr(c, 'currency', None) or ''
            # Get currency symbol from the country object or map
            currency_symbol = getattr(c, 'currency_symbol', None) or c.currency_symbol if hasattr(c, 'currency_symbol') else None
            if not currency_symbol and currency_code:
                currency_symbol = CURRENCY_SYMBOLS.get(currency_code, CURRENCY_SYMBOLS.get(iso2, '$'))
            if not currency_symbol:
                currency_symbol = CURRENCY_SYMBOLS.get(iso2, '$')
            # Default currency code if not available
            if not currency_code:
                currency_code = 'USD' if iso2 == 'US' else 'INR' if iso2 == 'IN' else 'USD'
            
            countries_data.append({
                'code': iso2,
                'name': c.name,
                'emoji': c.emoji or '🌐',
                'currency': currency_symbol,
                'currency_code': currency_code,
                'currency_symbol': currency_symbol,
            })
        return JsonResponse({'countries': countries_data})
    except Exception as e:
        logger.error(f"Error getting countries: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def get_states_api(request):
    """
    API endpoint to get states for a specific country.
    Query params: country_code (ISO2 code, e.g., 'US', 'IN')
    Returns JSON with state id, name, and state_code.
    
    GET /api/countries-states/states/?country_code=IN
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    if not COUNTRYSATECITY_AVAILABLE:
        return JsonResponse({'error': 'countrystatecity-countries package not installed'}, status=503)
    
    country_code = request.GET.get('country_code', '').upper()
    if not country_code:
        return JsonResponse({'error': 'country_code parameter is required'}, status=400)
    
    try:
        states = get_states_of_country(country_code)
        states_data = [
            {
                'id': s.id,
                'name': s.name,
                'state_code': s.state_code,
            }
            for s in states
        ]
        return JsonResponse({'states': states_data})
    except Exception as e:
        logger.error(f"Error getting states for country {country_code}: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def get_cities_api(request):
    """
    API endpoint to get cities for a specific state.
    Query params: country_code (ISO2), state_code (state code)
    Returns JSON with city id and name.
    
    GET /api/countries-states/cities/?country_code=IN&state_code=MH
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    if not COUNTRYSATECITY_AVAILABLE:
        return JsonResponse({'error': 'countrystatecity-countries package not installed'}, status=503)
    
    country_code = request.GET.get('country_code', '').upper()
    state_code = request.GET.get('state_code', '').upper()
    
    if not country_code or not state_code:
        return JsonResponse({'error': 'country_code and state_code parameters are required'}, status=400)
    
    try:
        cities = get_cities_of_state(country_code, state_code)
        cities_data = [
            {'id': c.id, 'name': c.name}
            for c in cities
        ]
        return JsonResponse({'cities': cities_data})
    except Exception as e:
        logger.error(f"Error getting cities for {country_code}-{state_code}: {e}")
        return JsonResponse({'error': str(e)}, status=500)
