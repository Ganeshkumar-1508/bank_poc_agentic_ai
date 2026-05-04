"""
Geolocation-related views and APIs.
Handles user region detection, session management, and region-based APIs.
"""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from ..views.base import (
    logger,
    get_user_region_from_session,
    update_user_session_with_region,
    get_all_countries,
    detect_user_region,
)
from ..views.geolocation_views import get_country_data


@csrf_exempt
def user_region_api(request):
    """
    API endpoint to get current user region.
    
    GET /api/user-region/
    Returns: Current region data as JSON
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        region_data = get_user_region_from_session(request)
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
    Returns: Updated region data as JSON
    """
    try:
        data = json.loads(request.body)
        country_code = data.get('country_code', '').upper()
        
        if not country_code:
            return JsonResponse({'error': 'country_code is required'}, status=400)
        
        # Validate country code
        all_countries = get_all_countries()
        if country_code not in all_countries:
            return JsonResponse({'error': f'Invalid country code: {country_code}'}, status=400)
        
        # Get full region data for the country
        country_info = get_country_data(country_code)
        
        # Detect additional region info from IP
        region_data = detect_user_region(request)
        region_data['country_code'] = country_code
        region_data['country_name'] = country_info['name']
        region_data['currency'] = country_info['currency']
        region_data['currency_code'] = country_info['currency_code']
        region_data['ddg_region'] = country_info['ddg_region']
        
        # Store in session
        request.session['user_region'] = region_data
        
        # Update UserSession model
        update_user_session_with_region(request, region_data)
        
        logger.info(f"Region manually set to {country_code} for session {request.session.session_key}")
        
        # Create response with JSON and set cookie for JavaScript access
        response = JsonResponse(region_data)
        response.set_cookie(
            'user_region',
            json.dumps({
                'code': country_code,
                'name': country_info['name'],
                'currency': country_info['currency'],
                'currency_code': country_info['currency_code']
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