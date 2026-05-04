"""
Django Middleware for Region Detection and Audit Context

This middleware detects user region on first request using ipinfo.io API
and stores region data in the session. Also provides audit context tracking.

Updated to use the geolocation utility functions from Test/utils/geolocation.py
matching the streamlit_ref/helpers.py logic.
"""

import json
import logging
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

# Import geolocation utilities
from utils.geolocation import detect_user_region_with_request, _get_client_ip

# Thread-local storage for audit context
_audit_context = threading.local()


class RegionDetectionMiddleware:
    """
    Middleware to detect user region on first request.

    Detects user's country using ipinfo.io API and stores region data
    in request.session['user_region']. Supports manual override via POST requests.
    Uses the geolocation utility functions from utils.geolocation.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Handle manual region override from POST requests
        if request.method == 'POST' and request.path == '/api/set-region/':
            # Manual override already handled by the view
            return self.get_response(request)

        # Detect region on first request if not already set
        if 'user_region' not in request.session:
            region_data = self._detect_region(request)
            request.session['user_region'] = region_data
            logger.info(f"Region detected for session {request.session.session_key}: {region_data['country_code']}")

        # Store region in request for easy access in views
        request.user_region = request.session['user_region']

        response = self.get_response(request)

        # Set cookie for JavaScript access if not already set
        if 'user_region' not in request.COOKIES:
            user_region = request.session['user_region']
            response.set_cookie(
                'user_region',
                json.dumps({
                    'code': user_region.get('country_code', 'WW'),
                    'name': user_region.get('country_name', 'Worldwide'),
                    'currency': user_region.get('currency_symbol', '$'),
                    'currency_code': user_region.get('currency_code', 'USD')
                }),
                max_age=86400 * 30, # 30 days
                httponly=False, # Allow JavaScript access
                samesite='Lax'
            )

        return response

    def _detect_region(self, request):
        """
        Detect user region using ipinfo.io API.
        Uses the detect_user_region_with_request function from utils.geolocation.

        Args:
            request: Django request object

        Returns:
            dict: Region data with country_code, country_name, city, currency_symbol,
                  currency_code, ddg_region, ip_address
        """
        # Use the geolocation utility function
        region_data = detect_user_region_with_request(request)
        
        # Ensure all expected fields are present
        fallback = {
            'country_code': 'WW',
            'country_name': 'Worldwide',
            'city': '',
            'ip_address': '',
            'currency_symbol': '',
            'currency_code': '',
            'ddg_region': 'wt-wt'
        }
        
        # Merge with fallback for any missing fields
        for key, value in fallback.items():
            if key not in region_data or region_data[key] is None:
                region_data[key] = value
                
        return region_data


# =============================================================================
# AUDIT CONTEXT MIDDLEWARE AND HELPERS
# =============================================================================

class AuditContextMiddleware:
    """
    Middleware to store current user and IP in thread-local storage
    for use in audit logging during model save operations.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Store user info in thread-local
        _audit_context.user_id = getattr(request.user, 'id', None)
        _audit_context.user_type = self._get_user_type(request)
        _audit_context.ip_address = self._get_client_ip(request)
        _audit_context.request = request

        response = self.get_response(request)

        # Clean up after response
        if hasattr(_audit_context, 'request'):
            del _audit_context.request

        return response

    def _get_user_type(self, request):
        """Determine user type for audit logging."""
        if hasattr(request, 'user') and request.user.is_authenticated:
            if request.user.is_staff:
                return 'ADMIN'
            return 'USER'
        return 'SYSTEM'

    def _get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')


# Helper functions for accessing audit context
def get_current_user_id():
    """Get current user ID from thread-local storage."""
    return getattr(_audit_context, 'user_id', None)


def get_current_user_type():
    """Get current user type from thread-local storage."""
    return getattr(_audit_context, 'user_type', 'SYSTEM')


def get_current_ip_address():
    """Get current IP address from thread-local storage."""
    return getattr(_audit_context, 'ip_address', None)


def get_current_request():
    """Get current request object from thread-local storage."""
    return getattr(_audit_context, 'request', None)
