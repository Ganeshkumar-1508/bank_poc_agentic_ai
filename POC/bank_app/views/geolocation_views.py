"""
Geolocation-related views and APIs.
Handles user region detection, session management, and region-based APIs.

Updated to use the geolocation utility functions from utils.geolocation
matching the streamlit_ref/helpers.py logic.
"""

import json
import logging

from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render

from utils.geolocation import (
    detect_user_region,
    detect_user_region_with_request,
    set_search_region,
    fetch_country_data,
    _get_client_ip,
)

logger = logging.getLogger(__name__)


# =============================================================================
# GEOLOCATION API ENDPOINTS
# =============================================================================

@csrf_exempt
@require_GET
def user_region_api(request):
    """
    API endpoint to get current user region.

    GET /api/user-region/
    Returns: Current region data as JSON (matching streamlit_ref format)
    """
    try:
        # Detect region using the updated function
        region_data = detect_user_region_with_request(request)
        return JsonResponse(region_data)
    except Exception as e:
        logger.error(f"Error getting user region: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def set_region_api(request):
    """
    API endpoint to manually set user region.

    POST /api/set-region/
    Body: {"country_code": "IN"}
    Returns: Updated region data as JSON (matching streamlit_ref format)
    """
    try:
        data = json.loads(request.body)
        country_code = data.get('country_code', '').upper()

        if not country_code:
            return JsonResponse({'error': 'country_code is required'}, status=400)

        # Get country data using fetch_country_data
        countries = fetch_country_data()
        
        if country_code not in countries:
            return JsonResponse({'error': f'Invalid country code: {country_code}'}, status=400)

        # Get country info
        country_info = countries.get(country_code, {})
        
        # Get ddg_region using set_search_region
        ddg_region = set_search_region(country_code)

        # Build region data matching streamlit_ref format
        region_data = {
            'country_code': country_code,
            'country_name': country_info.get('name', country_code),
            'ddg_region': ddg_region if isinstance(ddg_region, str) else ddg_region.get('region_code', ''),
            'currency_symbol': country_info.get('currency_symbol', ''),
            'currency_code': country_info.get('currency_code', ''),
            'ip_address': _get_client_ip(request),
            'city': '',  # Will be populated if detection is re-run
        }

        # Store in session
        request.session['user_region'] = region_data

        logger.info(f"Region manually set to {country_code} for session {request.session.session_key}")

        # Create response with JSON and set cookie for JavaScript access
        response = JsonResponse(region_data)
        response.set_cookie(
            'user_region',
            json.dumps({
                'code': country_code,
                'name': country_info.get('name', country_code),
                'currency': country_info.get('currency_symbol', ''),
                'currency_code': country_info.get('currency_code', '')
            }),
            max_age=86400 * 30,  # 30 days
            httponly=False,  # Allow JavaScript access
            samesite='Lax'
        )
        return response
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error setting user region: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def detect_region_view(request):
    """
    View to manually trigger region detection.

    GET /api/detect-region/
    Returns: Detected region data as JSON
    """
    try:
        region_data = detect_user_region_with_request(request)
        return JsonResponse(region_data)
    except Exception as e:
        logger.error(f"Error detecting region: {e}")
        return JsonResponse({'error': str(e)}, status=500)
