"""
Page rendering views for the Bank POC Agentic AI application.
Contains simple views that only render HTML templates without complex logic.
"""

from django.shortcuts import render
from .base import get_user_region_from_session, get_all_countries


def home(request):
    """Render the home page."""
    return render(request, 'bank_app/home.html')


def credit_risk(request):
    """Render the credit risk assessment page."""
    return render(request, 'bank_app/credit_risk.html')


def fd_advisor(request):
    """Render the FD Advisor page."""
    return render(request, 'bank_app/fd_advisor.html')


def mortgage_analytics(request):
    """Render the Mortgage Analytics page."""
    return render(request, 'bank_app/mortgage_analytics.html')


def emi_calculator(request):
    """Render the EMI Calculator page."""
    return render(request, 'bank_app/emi_calculator.html')


def emi(request):
    """Render the EMI page with tabs for Calculator and Amortization Schedule."""
    return render(request, 'bank_app/emi.html')


def financial_news(request):
    """Render the Financial News page."""
    return render(request, 'bank_app/financial_news.html')


def new_account(request):
    """Render the New Account page."""
    return render(request, 'bank_app/new_account.html')


def smart_assistant(request):
    """
    Smart Assistant Chat Interface
    
    A unified chat interface that routes user queries to appropriate crews
    based on intent classification using Router Crew.
    """
    # Get user region for context
    region_data = get_user_region_from_session(request)
    # get_all_countries() returns a dict keyed by country code, convert to list of tuples
    countries_dict = get_all_countries()
    country_list = [(code, info.get('name', code)) for code, info in countries_dict.items()]
    
    return render(request, 'bank_app/smart_assistant.html', {
        'user_region': region_data,
        'country_list': country_list,
    })
