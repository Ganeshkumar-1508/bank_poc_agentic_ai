"""
Context processors for the Bank POC Django app.
"""

from utils.geolocation import get_country_display_list


def countries_context(request):
    """
    Context processor to provide country list and user region to all templates.
    Returns the raw session data for user_region so templates can access
    .country_code, .country_name, .currency_symbol, etc.
    """
    # Get user region from session - return the raw dict, not a formatted string
    user_region = request.session.get('user_region', {})

    # If no region in session, provide a default empty dict (template will handle fallback)
    if not user_region:
        user_region = {}

    return {
        'country_list': get_country_display_list(),
        'user_region': user_region,
    }