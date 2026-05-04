"""
Base module for bank_app views.

Contains shared imports, constants, and helper functions used across all view modules.

Simplified version: Removed lazy loading infrastructure for CrewAI.
CrewAI functions are now imported directly in crew_api_views.py.
This module keeps:
- EMI calculator functions
- Geolocation helper functions (including country/state/city data)
- Basic logging and configuration
"""

import os
import sys
import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional

import numpy as np
import joblib

from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

# Import UserSession model (lazy import to avoid circular imports)
UserSession = None
try:
    from .models import UserSession
except ImportError:
    pass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# PATH CONFIGURATION
# =============================================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# =============================================================================
# MODEL PATHS
# =============================================================================

INDIAN_MODEL_PATH = os.path.join(BASE_DIR, "models", "credit_risk", "indian", "loan_model.pkl")
INDIAN_SCALER_PATH = os.path.join(BASE_DIR, "models", "credit_risk", "indian", "scaler.pkl")
US_MODEL_PATH = os.path.join(BASE_DIR, "models", "credit_risk", "xgb_model.pkl")

# =============================================================================
# COUNTRY/STATE/CITY DATA (simplified - in production, use a database)
# =============================================================================

COUNTRYSATECITY_AVAILABLE = True

# Minimal country data for dropdowns
_COUNTRIES_DATA = {
    "IN": {"name": "India", "currency": "₹", "currency_code": "INR", "ddg_region": "India", "states": ["Andhra Pradesh", "Karnataka", "Maharashtra", "Tamil Nadu", "Telangana"]},
    "US": {"name": "United States", "currency": "$", "currency_code": "USD", "ddg_region": "United States", "states": ["California", "New York", "Texas", "Florida"]},
    "GB": {"name": "United Kingdom", "currency": "£", "currency_code": "GBP", "ddg_region": "United Kingdom", "states": ["England", "Scotland", "Wales"]},
    "CA": {"name": "Canada", "currency": "$", "currency_code": "CAD", "ddg_region": "Canada", "states": ["Ontario", "Quebec", "British Columbia"]},
    "AU": {"name": "Australia", "currency": "$", "currency_code": "AUD", "ddg_region": "Australia", "states": ["New South Wales", "Victoria", "Queensland"]},
}

def get_all_countries():
    """Return all available countries data."""
    return _COUNTRIES_DATA

def get_country_data(country_code):
    """Get data for a specific country."""
    return _COUNTRIES_DATA.get(country_code.upper(), {})

def get_countries():
    """Return list of country codes."""
    return list(_COUNTRIES_DATA.keys())

def get_states_of_country(country_code):
    """Get states for a specific country."""
    country = get_country_data(country_code)
    return country.get("states", [])

def get_cities_of_state(country_code, state_code):
    """Get cities for a specific state (simplified - returns empty list)."""
    # In production, this would query a database
    return []

# =============================================================================
# GEOLOCATION HELPER FUNCTIONS
# =============================================================================


def get_user_region_from_session(request):
    """
    Get user region from session or detect if not present.

    Args:
        request: Django request object

    Returns:
        dict: Region data with country_code, country_name, city, etc.
    """
    # Try to get from request attribute first
    if hasattr(request, "user_region"):
        return request.user_region

    # Fallback: check session
    if "user_region" in request.session:
        return request.session["user_region"]

    # Detect and store
    region_data = detect_user_region(request)
    request.session["user_region"] = region_data
    return region_data


def update_user_session_with_region(request, region_data):
    """
    Update or create UserSession with region data.

    Args:
        request: Django request object
        region_data: dict with region information
    """
    try:
        from .models import UserSession
    except ImportError:
        # Models not available
        return

    session_id = request.session.session_key or "anonymous"

    session, created = UserSession.objects.get_or_create(
        session_id=session_id,
        defaults={
            "user_ip": region_data.get("ip_address", ""),
            "country_code": region_data.get("country_code", ""),
            "country_name": region_data.get("country_name", ""),
            "city": region_data.get("city", ""),
            "region": region_data.get("region", ""),
            "ip_address": region_data.get("ip_address", ""),
            "session_data": {},
        },
    )

    if not created:
        session.user_ip = region_data.get("user_ip", session.user_ip)
        session.country_code = region_data.get("country_code", session.country_code)
        session.country_name = region_data.get("country_name", session.country_name)
        session.city = region_data.get("city", session.city)
        session.region = region_data.get("region", session.region)
        session.ip_address = region_data.get("ip_address", session.ip_address)
        session.save()


def detect_user_region(request):
    """
    Detect user's region from IP address.

    Args:
        request: Django request object

    Returns:
        dict: Region data
    """
    # Get IP address
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(",")[0]
    else:
        ip_address = request.META.get("REMOTE_ADDR", "")

    # Default region
    region_data = {
        "ip_address": ip_address,
        "country_code": "IN",
        "country_name": "India",
        "city": "",
        "region": "India",
        "currency": "₹",
    }

    # Try to get geolocation data
    try:
        from utils.geolocation import detect_region

        geolocation_data = detect_region(ip_address)
        if geolocation_data:
            region_data.update(geolocation_data)
    except ImportError:
        logger.warning("Geolocation module not available")
    except Exception as e:
        logger.warning(f"Geolocation detection failed: {e}")

    return region_data


def set_search_region(region):
    """Set search region (for CrewAI compatibility - no-op in simplified version)."""
    pass


def format_region_for_display(region_data):
    """Format region data for display."""
    return f"{region_data.get('city', '')}, {region_data.get('country_name', '')}"


def fetch_country_data(country_code):
    """Fetch country data (alias for get_country_data)."""
    return get_country_data(country_code)


# =============================================================================
# EMI CALCULATOR FUNCTIONS
# =============================================================================


def calculate_emi(
    loan_amount: float,
    interest_rate: float,
    tenure_months: int,
    method: str = "Reducing Balance",
    processing_fee: float = 0,
) -> dict:
    """
    Calculate EMI using three different methods.

    Args:
        loan_amount: Principal loan amount in INR
        interest_rate: Annual interest rate (%)
        tenure_months: Loan tenure in months
        method: Calculation method - "Reducing Balance", "Flat Rate", or "Compound Interest"
        processing_fee: Processing fee in INR

    Returns:
        Dictionary with EMI, total interest, total cost, and amortization schedule
    """
    if loan_amount <= 0 or interest_rate <= 0 or tenure_months <= 0:
        return {"error": "Invalid input values. All values must be positive."}

    if method == "Reducing Balance":
        emi, total_interest = _calculate_reducing_balance_emi(
            loan_amount, interest_rate, tenure_months
        )
    elif method == "Flat Rate":
        emi, total_interest = _calculate_flat_rate_emi(
            loan_amount, interest_rate, tenure_months
        )
    elif method == "Compound Interest":
        emi, total_interest = _calculate_compound_interest_emi(
            loan_amount, interest_rate, tenure_months
        )
    else:
        return {"error": f"Unknown calculation method: {method}"}

    total_cost = loan_amount + total_interest + processing_fee

    # Generate amortization schedule
    amortization_schedule = generate_amortization_schedule(
        loan_amount, interest_rate, tenure_months, method, emi
    )

    return {
        "loan_amount": loan_amount,
        "interest_rate": interest_rate,
        "tenure_months": tenure_months,
        "method": method,
        "monthly_emi": round(emi, 2),
        "total_interest": round(total_interest, 2),
        "total_cost": round(total_cost, 2),
        "processing_fee": processing_fee,
        "amortization_schedule": amortization_schedule,
    }


def _calculate_reducing_balance_emi(
    principal: float, annual_rate: float, months: int
) -> tuple:
    """
    Calculate EMI using reducing balance method (most common in India).

    Formula: EMI = P * r * (1 + r)^n / ((1 + r)^n - 1)
    where r = monthly interest rate, n = tenure in months
    """
    monthly_rate = annual_rate / 12 / 100
    emi = (
        principal * monthly_rate * (1 + monthly_rate) ** months
        / ((1 + monthly_rate) ** months - 1)
    )
    total_payment = emi * months
    total_interest = total_payment - principal
    return emi, total_interest


def _calculate_flat_rate_emi(
    principal: float, annual_rate: float, months: int
) -> tuple:
    """
    Calculate EMI using flat rate method.

    Formula: Total Interest = P * r * t
    EMI = (Principal + Total Interest) / n
    """
    annual_rate_decimal = annual_rate / 100
    total_interest = principal * annual_rate_decimal * (months / 12)
    total_payment = principal + total_interest
    emi = total_payment / months
    return emi, total_interest


def _calculate_compound_interest_emi(
    principal: float, annual_rate: float, months: int
) -> tuple:
    """
    Calculate EMI using compound interest method.

    Formula: A = P * (1 + r/n)^(n*t)
    Where interest is compounded monthly
    """
    monthly_rate = annual_rate / 12 / 100
    amount = principal * (1 + monthly_rate) ** months
    total_interest = amount - principal
    emi = amount / months
    return emi, total_interest


def generate_amortization_schedule(
    loan_amount: float,
    interest_rate: float,
    tenure_months: int,
    method: str,
    monthly_emi: float,
) -> list:
    """
    Generate year-by-year amortization schedule.

    Returns:
        List of dictionaries with year, opening_balance, principal_paid, interest_paid, total_paid, closing_balance
    """
    schedule = []
    remaining_balance = loan_amount
    monthly_rate = interest_rate / 12 / 100

    year_data = {}
    current_year = 1

    for month in range(1, tenure_months + 1):
        if method == "Reducing Balance":
            interest_payment = remaining_balance * monthly_rate
            principal_payment = monthly_emi - interest_payment
        elif method == "Flat Rate":
            # For flat rate, interest is pre-calculated and evenly distributed
            interest_payment = monthly_emi * 0.3  # Approximate split
            principal_payment = monthly_emi - interest_payment
        else:
            interest_payment = remaining_balance * monthly_rate
            principal_payment = monthly_emi - interest_payment

        # Ensure principal payment doesn't exceed remaining balance
        if principal_payment > remaining_balance:
            principal_payment = remaining_balance
            monthly_emi = principal_payment + interest_payment

        remaining_balance -= principal_payment

        # Track yearly data
        if current_year not in year_data:
            year_data[current_year] = {
                "opening_balance": loan_amount if month == 1 else year_data[current_year - 1]["closing_balance"],
                "principal_paid": 0,
                "interest_paid": 0,
                "total_paid": 0,
            }

        year_data[current_year]["principal_paid"] += principal_payment
        year_data[current_year]["interest_paid"] += interest_payment
        year_data[current_year]["total_paid"] += monthly_emi

        # Move to next year
        if month % 12 == 0:
            year_data[current_year]["closing_balance"] = max(0, remaining_balance)
            schedule.append(
                {
                    "Year": current_year,
                    "Opening Balance": round(year_data[current_year]["opening_balance"], 2),
                    "Principal Paid": round(year_data[current_year]["principal_paid"], 2),
                    "Interest Paid": round(year_data[current_year]["interest_paid"], 2),
                    "Total Paid": round(year_data[current_year]["total_paid"], 2),
                    "Closing Balance": round(year_data[current_year]["closing_balance"], 2),
                }
            )
            current_year += 1

    # Add final year if tenure is not a multiple of 12
    if tenure_months % 12 != 0 and remaining_balance > 0:
        year_data[current_year] = {
            "opening_balance": year_data[current_year - 1]["closing_balance"] if current_year > 1 else loan_amount,
            "principal_paid": 0,
            "interest_paid": 0,
            "total_paid": 0,
            "closing_balance": 0,
        }
        # Recalculate for remaining months
        for month in range((current_year - 1) * 12 + 1, tenure_months + 1):
            interest_payment = remaining_balance * monthly_rate
            principal_payment = monthly_emi - interest_payment
            if principal_payment > remaining_balance:
                principal_payment = remaining_balance
            remaining_balance -= principal_payment
            year_data[current_year]["principal_paid"] += principal_payment
            year_data[current_year]["interest_paid"] += interest_payment
            year_data[current_year]["total_paid"] += monthly_emi

        schedule.append(
            {
                "Year": current_year,
                "Opening Balance": round(year_data[current_year]["opening_balance"], 2),
                "Principal Paid": round(year_data[current_year]["principal_paid"], 2),
                "Interest Paid": round(year_data[current_year]["interest_paid"], 2),
                "Total Paid": round(year_data[current_year]["total_paid"], 2),
                "Closing Balance": round(year_data[current_year]["closing_balance"], 2),
            }
        )

    return schedule
