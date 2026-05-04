"""
Django Middleware for Region Detection and Audit Context

This middleware detects user region on first request using ipinfo.io API
and stores region data in the session. Also provides audit context tracking.
"""

import json
import logging
import threading
import urllib.request
import urllib.error

from django.conf import settings

logger = logging.getLogger(__name__)

# Thread-local storage for audit context
_audit_context = threading.local()


class RegionDetectionMiddleware:
    """
    Middleware to detect user region on first request.

    Detects user's country using ipinfo.io API and stores region data
    in request.session['user_region']. Supports manual override via POST requests.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.api_url = "https://ipinfo.io/json"

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
            import json
            user_region = request.session['user_region']
            response.set_cookie(
                'user_region',
                json.dumps({
                    'code': user_region.get('country_code', 'WW'),
                    'name': user_region.get('country_name', 'Worldwide'),
                    'currency': user_region.get('currency', '$'),
                    'currency_code': user_region.get('currency_code', 'USD')
                }),
                max_age=86400 * 30,  # 30 days
                httponly=False,  # Allow JavaScript access
                samesite='Lax'
            )
        
        return response

    def _detect_region(self, request):
        """
        Detect user region using ipinfo.io API.

        Args:
            request: Django request object

        Returns:
            dict: Region data with country_code, country_name, city, region, ip_address
        """
        # Default fallback region
        fallback_region = {
            'country_code': 'WW',
            'country_name': 'Worldwide',
            'city': '',
            'region': '',
            'ip_address': '',
            'currency': '$',
            'currency_code': 'USD',
            'ddg_region': 'en_US'
        }

        # Get client IP address
        client_ip = self._get_client_ip(request)
        fallback_region['ip_address'] = client_ip

        try:
            # Make request to ipinfo.io
            req = urllib.request.Request(
                f"{self.api_url}?token={getattr(settings, 'IPINFO_TOKEN', '')}",
                headers={'User-Agent': 'Mozilla/5.0'}
            )

            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))

                country_code = data.get('country', 'WW')
                country_name = data.get('country_name', 'Worldwide')
                city = data.get('city', '')
                region = data.get('region', '')

                # Map country code to region settings
                country_data = self._get_country_data(country_code)

                return {
                    'country_code': country_code,
                    'country_name': country_name,
                    'city': city,
                    'region': region,
                    'ip_address': client_ip,
                    'currency': country_data.get('currency', '$'),
                    'currency_code': country_data.get('currency_code', 'USD'),
                    'ddg_region': country_data.get('ddg_region', 'en_US')
                }

        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
            logger.warning(f"IP geolocation API failed: {e}. Using fallback region.")
            return fallback_region

    def _get_client_ip(self, request):
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

    def _get_country_data(self, country_code):
        """
        Get country data including currency and search region settings.

        Args:
            country_code: ISO 3166-1 alpha-2 country code

        Returns:
            dict: Country data with currency and region info
        """
        country_data = {
            'IN': {
                'code': 'IN',
                'name': 'India',
                'currency': '₹',
                'currency_code': 'INR',
                'ddg_region': 'in_en'
            },
            'US': {
                'code': 'US',
                'name': 'United States',
                'currency': '$',
                'currency_code': 'USD',
                'ddg_region': 'en_US'
            },
            'UK': {
                'code': 'UK',
                'name': 'United Kingdom',
                'currency': '£',
                'currency_code': 'GBP',
                'ddg_region': 'uk_en'
            },
            'CA': {
                'code': 'CA',
                'name': 'Canada',
                'currency': '$',
                'currency_code': 'CAD',
                'ddg_region': 'ca_en'
            },
            'AU': {
                'code': 'AU',
                'name': 'Australia',
                'currency': '$',
                'currency_code': 'AUD',
                'ddg_region': 'au_en'
            },
            'DE': {
                'code': 'DE',
                'name': 'Germany',
                'currency': '€',
                'currency_code': 'EUR',
                'ddg_region': 'de_de'
            },
            'FR': {
                'code': 'FR',
                'name': 'France',
                'currency': '€',
                'currency_code': 'EUR',
                'ddg_region': 'fr_fr'
            },
            'WW': {
                'code': 'WW',
                'name': 'Worldwide',
                'currency': '$',
                'currency_code': 'USD',
                'ddg_region': 'en_US'
            }
        }

        return country_data.get(country_code, country_data['WW'])


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
