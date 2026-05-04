from django.urls import path

# Modular view imports from the views package
from .views import (
# Page views
home,
credit_risk,
fd_advisor,
mortgage_analytics,
emi_calculator,
emi,
financial_news,
new_account,
smart_assistant,
# API views
credit_risk_api,
credit_risk_indian_api,
credit_risk_us_api,
emi_calculator_api,
kyc_verify_api,
compliance_check_api,
rag_query_api,
fd_rates_api,
product_analysis_api,
get_countries_api,
get_states_api,
get_cities_api,
financial_news_api,
mortgage_calculator_api,
loan_application_api,
fd_advisor_crew_api,
credit_risk_crew_api,
aml_crew_api,
financial_news_crew_api,
router_crew_api,
loan_creation_crew_api,
mortgage_analytics_crew_api,
fd_template_crew_api,
visualization_crew_api,
analysis_crew_api,
database_crew_api,
smart_assistant_query,
user_region_api,
set_region_api,
loan_crewai_decision_api,
td_fd_creation_api,
)

# Import mortgage analytics views for PDF export
from .views.mortgage_analytics_views import mortgage_pdf_export

from . import api_views
from .views.crew_api_views import run_crew

urlpatterns = [
    # Page renderers
    path('', home, name='home'),
    path('credit-risk/', credit_risk, name='credit_risk'),
    path('fd-advisor/', fd_advisor, name='fd_advisor'),
    path('mortgage-analytics/', mortgage_analytics, name='mortgage_analytics'),
    path('financial-news/', financial_news, name='financial_news'),
    path('new-account/', new_account, name='new_account'),
    path('emi/', emi, name='emi'),
    path('emi-calculator/', emi_calculator, name='emi_calculator'),
    path('smart-assistant/', smart_assistant, name='smart_assistant'),

    # Credit Risk API endpoints
    path('api/credit-risk/', credit_risk_api, name='credit_risk_api'),
    path('api/credit-risk/indian/', credit_risk_indian_api, name='credit_risk_indian_api'),
    path('api/credit-risk/us/', credit_risk_us_api, name='credit_risk_us_api'),

    # EMI Calculator API endpoint
    path('api/emi-calculate/', emi_calculator_api, name='emi_calculator_api'),

    # KYC API endpoint
    path('api/kyc-verify/', kyc_verify_api, name='kyc_verify_api'),

    # Compliance (AML/PEP) API endpoint
    path('api/compliance-check/', compliance_check_api, name='compliance_check_api'),

    # RAG Engine API endpoint
    path('api/rag-query/', rag_query_api, name='rag_query_api'),

    # FD Advisor API endpoints
    path('api/fd-rates/', fd_rates_api, name='fd_rates_api'),
    path('api/product-analysis/', product_analysis_api, name='product_analysis_api'),

    # Countries-States-Cities API endpoints
    path('api/csc/countries/', get_countries_api, name='get_countries_api'),
    path('api/csc/states/', get_states_api, name='get_states_api'),
    path('api/csc/cities/', get_cities_api, name='get_cities_api'),

    # Financial News API endpoint
    path('api/financial-news/', financial_news_api, name='financial_news_api'),

    # Mortgage Analytics API endpoint
    path('api/mortgage-calculate/', mortgage_calculator_api, name='mortgage_calculator_api'),

    # Loan Application API endpoint
    path('api/loan-apply/', loan_application_api, name='loan_application_api'),

    # =============================================================================
    # CREWAI CREW EXECUTION API ENDPOINTS
    # =============================================================================

    # NEW: Generic CrewAI execution endpoint (replaces all 11 previous endpoints)
    path('api/run-crew/', run_crew, name='run_crew'),

    # DEPRECATED: Legacy endpoints kept for backward compatibility during migration
    # These will be removed in a future version. Use /api/run-crew/ instead with crew_type parameter.
    path('api/fd-advisor-crew/', fd_advisor_crew_api, name='fd_advisor_crew_api'),
    path('api/credit-risk-crew/', credit_risk_crew_api, name='credit_risk_crew_api'),
    path('api/aml-crew/', aml_crew_api, name='aml_crew_api'),
    path('api/financial-news-crew/', financial_news_crew_api, name='financial_news_crew_api'),
    path('api/router/', router_crew_api, name='router_crew'),
    path('api/loan-creation/', loan_creation_crew_api, name='loan_creation_crew'),
    path('api/mortgage-analytics-crew/', mortgage_analytics_crew_api, name='mortgage_analytics_crew'),
    path('api/fd-template/', fd_template_crew_api, name='fd_template_crew'),
    path('api/visualization/', visualization_crew_api, name='visualization_crew'),
    path('api/analysis/', analysis_crew_api, name='analysis_crew'),
    path('api/database-query/', database_crew_api, name='database_crew'),
    path('api/smart-assistant-query/', smart_assistant_query, name='smart_assistant_query'),

    # =============================================================================
    # GEOLOCATION API ENDPOINTS
    # =============================================================================

    # Get current user region
    path('api/user-region/', user_region_api, name='user_region_api'),

    # Set user region manually
    path('api/set-region/', set_region_api, name='set_region_api'),
    
    # =============================================================================
    # NEW RESTFUL AJAX API ENDPOINTS
    # =============================================================================
    
    # Loan CRUD endpoints
    path('api/loans/', api_views.loan_list_api, name='loan_list_api'),
    path('api/loans/create/', api_views.loan_create_api, name='loan_create_api'),
    path('api/loans/<int:loan_id>/', api_views.loan_detail_api, name='loan_detail_api'),
    path('api/loans/<int:loan_id>/update/', api_views.loan_update_api, name='loan_update_api'),
    path('api/loans/<int:loan_id>/delete/', api_views.loan_delete_api, name='loan_delete_api'),
    
    # Loan status update endpoints
    path('api/loans/<int:loan_id>/submit/', api_views.loan_submit_api, name='loan_submit_api'),
    path('api/loans/<int:loan_id>/approve/', api_views.loan_approve_api, name='loan_approve_api'),
    path('api/loans/<int:loan_id>/reject/', api_views.loan_reject_api, name='loan_reject_api'),
    
    # Bulk operations endpoints
    path('api/loans/bulk-approve/', api_views.bulk_loan_approve_api, name='bulk_loan_approve_api'),
    path('api/loans/bulk-reject/', api_views.bulk_loan_reject_api, name='bulk_loan_reject_api'),
    
    # Dashboard data endpoints
    path('api/dashboard/stats/', api_views.dashboard_stats_api, name='dashboard_stats_api'),
    path('api/dashboard/charts/', api_views.dashboard_charts_api, name='dashboard_charts_api'),
    
    # CrewAI automated decision endpoint
    path('api/loans/<int:loan_id>/crewai-decision/', loan_crewai_decision_api, name='loan_crewai_decision_api'),

    # TD/FD Creation API endpoint
    path('api/td-fd-creation/', td_fd_creation_api, name='td_fd_creation_api'),
    
    # Country list API (renamed to match actual function name)
    path('api/country-list/', get_countries_api, name='country_list_api'),
    
    # =============================================================================
    # MORTGAGE ANALYTICS PDF EXPORT
    # =============================================================================
    path('mortgage-analytics/pdf/', mortgage_pdf_export, name='mortgage_pdf_export'),
    ]
