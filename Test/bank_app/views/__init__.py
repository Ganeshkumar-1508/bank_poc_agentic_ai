"""
Bank App Views Package - Modular Views Structure

This package replaces the monolithic views.py file with a modular structure
organized by feature areas. All views are re-exported here for backward
compatibility with existing URL configurations.

Module Structure:
- base.py: Shared imports, constants, and helper functions
- page_views.py: Simple page rendering views
- geolocation_views.py: Geolocation-related views and APIs
- country_state_city_views.py: Countries-States-Cities API endpoints
- crew_api_views.py: All 11 CrewAI-powered API endpoints
- credit_risk_views.py: Credit risk assessment endpoints
- fd_advisor_views.py: FD rates and TD/FD creation endpoints
- financial_news_views.py: Financial news API endpoints
- emi_calculator_views.py: EMI and mortgage calculator endpoints
- smart_assistant_views.py: Smart assistant chat endpoints
- legacy_api_views.py: Legacy API endpoints for backward compatibility
- decision_views.py: Loan decision endpoints
"""

# Re-export everything from base module (shared helpers, constants)
from .base import (
    logger,
    BASE_DIR,
    INDIAN_MODEL_PATH,
    INDIAN_SCALER_PATH,
    US_MODEL_PATH,
    COUNTRYSATECITY_AVAILABLE,
    get_user_region_from_session,
    update_user_session_with_region,
    calculate_emi,
    get_countries,
    get_states_of_country,
    get_cities_of_state,
    get_country_data,
    get_all_countries,
    detect_user_region,
    set_search_region,
    format_region_for_display,
    fetch_country_data,
    UserSession,
)

# Re-export page views
from .page_views import (
    home,
    credit_risk,
    fd_advisor,
    mortgage_analytics,
    emi_calculator,
    emi,
    financial_news,
    new_account,
    smart_assistant,
)

# Re-export geolocation views
from .geolocation_views import (
    user_region_api,
    set_region_api,
)

# Re-export country/state/city views
from .country_state_city_views import (
    get_countries_api,
    get_states_api,
    get_cities_api,
)

# Re-export CrewAI API views - both new generic and legacy endpoints
# Note: credit_risk_crew_api is imported from credit_risk_views.py below
from .crew_api_views import (
    run_crew,
    fd_advisor_crew_api,
    aml_crew_api,
    financial_news_crew_api,
    router_crew_api,
    loan_creation_crew_api,
    mortgage_analytics_crew_api,
    fd_template_crew_api,
    visualization_crew_api,
    analysis_crew_api,
    database_crew_api,
)

# Re-export credit risk views
from .credit_risk_views import (
    credit_risk_indian_api,
    credit_risk_us_api,
    credit_risk_api,
    credit_risk_crew_api,  # This overrides the one from crew_api_views
)

# Re-export FD advisor views
from .fd_advisor_views import (
fd_rates_api,
product_analysis_api,
td_fd_creation_api,
send_fd_confirmation_email,
)

# Re-export financial news views
from .financial_news_views import (
    countries_api,
    financial_news_api,
)

# Re-export EMI calculator views
from .emi_calculator_views import (
emi_calculator_api,
mortgage_calculator_api,
loan_application_api,
)

# Re-export mortgage analytics views
from .mortgage_analytics_views import (
mortgage_pdf_export,
)

# Re-export smart assistant views
from .smart_assistant_views import (
    smart_assistant_query,
)

# Re-export legacy API views
from .legacy_api_views import (
    kyc_verify_api,
    compliance_check_api,
    rag_query_api,
)

# Re-export decision views
from .decision_views import (
    loan_crewai_decision_api,
)

__all__ = [
    # Base
    'logger',
    'BASE_DIR',
    'INDIAN_MODEL_PATH',
    'INDIAN_SCALER_PATH',
    'US_MODEL_PATH',
    'CREWAI_AVAILABLE',
    'COUNTRYSATECITY_AVAILABLE',
    'parse_crew_output',
    'format_crew_response',
    'get_user_region_from_session',
    'update_user_session_with_region',
    'calculate_emi',
    'Crew',
    'Process',
    'get_countries',
    'get_states_of_country',
    'get_cities_of_state',
    'get_country_data',
    'get_all_countries',
    'detect_user_region',
    'set_search_region',
    'format_region_for_display',
    'fetch_country_data',
    'UserSession',
    
    # Page views
    'home',
    'credit_risk',
    'fd_advisor',
    'mortgage_analytics',
    'emi_calculator',
    'emi',
    'financial_news',
    'new_account',
    'smart_assistant',
    
    # Geolocation views
    'user_region_api',
    'set_region_api',
    
    # Country/State/City views
    'get_countries_api',
    'get_states_api',
    'get_cities_api',
    
    # CrewAI API views
    'fd_advisor_crew_api',
    'credit_risk_crew_api',
    'aml_crew_api',
    'financial_news_crew_api',
    'router_crew_api',
    'loan_creation_crew_api',
    'mortgage_analytics_crew_api',
    'fd_template_crew_api',
    'visualization_crew_api',
    'analysis_crew_api',
    'database_crew_api',
    
    # Credit risk views
    'credit_risk_indian_api',
    'credit_risk_us_api',
    'credit_risk_api',
    
    # FD advisor views
    'fd_rates_api',
    'product_analysis_api',
    'td_fd_creation_api',
    'send_fd_confirmation_email',
    
    # Financial news views
    'countries_api',
    'financial_news_api',
    
    # EMI calculator views
    'emi_calculator_api',
    'mortgage_calculator_api',
    'loan_application_api',
    
    # Mortgage analytics views
    'mortgage_pdf_export',
    
    # Smart assistant views
    'smart_assistant_query',
    
    # Legacy API views
    'kyc_verify_api',
    'compliance_check_api',
    'rag_query_api',
    
    # Decision views
    'loan_crewai_decision_api',
]
