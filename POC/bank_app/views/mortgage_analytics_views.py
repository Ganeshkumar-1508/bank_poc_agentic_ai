"""
Mortgage Analytics Views.
Contains endpoints for mortgage calculations, analysis, and PDF report generation.
"""

import os
import json
import logging
import traceback
import re
from datetime import datetime
from decimal import Decimal
from io import BytesIO

import markdown

from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils import timezone

from .base import logger

logger = logging.getLogger(__name__)

# =============================================================================
# Markdown Rendering Utilities
# =============================================================================

def render_markdown(text):
    """
    Render markdown text to HTML using Python markdown library.
    Follows the same pattern as FD Advisor with extensions:
    fenced_code, tables, nl2br, extra, codehilite
    
    Args:
        text: Markdown text to render
        
    Returns:
        HTML string
    """
    if not text:
        return ''
    
    try:
        return markdown.markdown(
            text,
            extensions=['fenced_code', 'tables', 'nl2br', 'extra', 'codehilite']
        )
    except Exception as e:
        logger.error(f"Error rendering markdown: {e}")
        return f"<p>Error rendering content: {str(e)}</p>"


def generate_mortgage_summary_markdown(mortgage_data, crew_output=None):
    """
    Generate a markdown summary for mortgage analytics.
    
    Args:
        mortgage_data: Dictionary with mortgage calculation data
        crew_output: Full CrewAI agent output (optional)
        
    Returns:
        Dictionary with 'summary_markdown', 'summary_html', 'structured_data', and 'full_agent_output'
    """
    currency_symbol = mortgage_data.get('currency_symbol', '$')
    loan_amount = mortgage_data.get('loan_amount', 0)
    interest_rate = mortgage_data.get('interest_rate', 0)
    term_years = mortgage_data.get('term_years', 30)
    down_payment = mortgage_data.get('down_payment', 0)
    home_price = mortgage_data.get('home_price', loan_amount + down_payment)
    monthly_payment = mortgage_data.get('monthly_payment', 0)
    total_interest = mortgage_data.get('total_interest', 0)
    total_payment = mortgage_data.get('total_payment', 0)
    
    # Extract borrower info
    credit_score = mortgage_data.get('credit_score', 740)
    dti_ratio = mortgage_data.get('dti_ratio', 35)
    loan_purpose = mortgage_data.get('loan_purpose', 'Purchase')
    property_type = mortgage_data.get('property_type', 'Single Family')
    
    # If crew output is available, use it as the primary summary
    if crew_output:
        crew_output_str = crew_output if isinstance(crew_output, str) else str(crew_output)
        summary_md = crew_output_str
        full_agent_output = crew_output_str
    else:
        # Generate markdown summary from calculated data
        summary_md = f"""**Mortgage Analysis Summary**

## Loan Details

| Parameter | Value |
|-----------|-------|
| Home Price | {currency_symbol}{home_price:,.0f} |
| Down Payment | {currency_symbol}{down_payment:,.0f} |
| Loan Amount | {currency_symbol}{loan_amount:,.0f} |
| Interest Rate | {interest_rate}% |
| Loan Term | {term_years} years ({term_years * 12} months) |

## Payment Breakdown

| Metric | Amount |
|--------|--------|
| Monthly Payment | {currency_symbol}{monthly_payment:,.2f} |
| Total Interest | {currency_symbol}{total_interest:,.0f} |
| Total Payment | {currency_symbol}{total_payment:,.0f} |

## Borrower Profile

- **Credit Score:** {credit_score}
- **Debt-to-Income Ratio:** {dti_ratio}%
- **Loan Purpose:** {loan_purpose}
- **Property Type:** {property_type}

**Recommendation:** Based on your credit score of {credit_score}, you qualify for competitive rates. Consider making a larger down payment to reduce your monthly obligation.
"""
        full_agent_output = None
    
    # Pre-render markdown to HTML
    summary_html = render_markdown(summary_md)
    
    # Build structured data for table display
    structured_data = {
        'loan_details': {
            'home_price': home_price,
            'down_payment': down_payment,
            'loan_amount': loan_amount,
            'interest_rate': interest_rate,
            'term_years': term_years,
            'term_months': term_years * 12
        },
        'payment_summary': {
            'monthly_payment': round(monthly_payment, 2),
            'total_interest': round(total_interest, 2),
            'total_payment': round(total_payment, 2)
        },
        'borrower_profile': {
            'credit_score': credit_score,
            'dti_ratio': dti_ratio,
            'loan_purpose': loan_purpose,
            'property_type': property_type
        }
    }
    
    return {
        'summary_markdown': summary_md,
        'summary_html': summary_html,
        'structured_data': structured_data,
        'full_agent_output': full_agent_output
    }


# =============================================================================
# Mortgage Analytics API Endpoints
# =============================================================================

@csrf_exempt
@require_POST
def mortgage_analytics_crew_api(request):
    """
    Mortgage Analytics CrewAI API endpoint.
    
    POST /api/mortgage-analytics-crew/
    Body: {
        "query": {
            "original_upb": 300000,
            "original_ltv": 80,
            "original_interest_rate": 6.5,
            "original_loan_term": 360,
            "borrower_credit_score": 740,
            "debt_to_income": 35,
            ...
        },
        "region": "United States"
    }
    
    Returns:
        JSON with markdown summary, HTML preview, and structured data
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        query = data.get('query', {})
        region = data.get('region', 'United States')
        
        # Extract mortgage parameters
        loan_amount = query.get('original_upb', 300000)
        interest_rate = query.get('original_interest_rate', 6.5)
        term_months = query.get('original_loan_term', 360)
        down_payment = query.get('down_payment', loan_amount * 0.2)
        credit_score = query.get('borrower_credit_score', 740)
        dti_ratio = query.get('debt_to_income', 35)
        loan_purpose = query.get('loan_purpose', 'Purchase')
        property_type = query.get('property_type', 'Single Family')
        
        # Calculate mortgage values
        term_years = term_months // 12
        home_price = loan_amount + down_payment
        monthly_rate = interest_rate / 100 / 12
        num_payments = term_months
        
        if monthly_rate > 0:
            monthly_payment = loan_amount * monthly_rate * pow(1 + monthly_rate, num_payments) / (pow(1 + monthly_rate, num_payments) - 1)
        else:
            monthly_payment = loan_amount / num_payments
        
        total_payment = monthly_payment * num_payments
        total_interest = total_payment - loan_amount
        
        # Build mortgage data dictionary
        mortgage_data = {
            'loan_amount': loan_amount,
            'interest_rate': interest_rate,
            'term_years': term_years,
            'down_payment': down_payment,
            'home_price': home_price,
            'monthly_payment': monthly_payment,
            'total_interest': total_interest,
            'total_payment': total_payment,
            'credit_score': credit_score,
            'dti_ratio': dti_ratio,
            'loan_purpose': loan_purpose,
            'property_type': property_type,
            'currency_symbol': '$'
        }
        
        # Try to get crew output if available
        crew_output = None
        if 'crew_output' in data:
            crew_output = data['crew_output']
        
        # Generate markdown summary
        result = generate_mortgage_summary_markdown(mortgage_data, crew_output)
        
        # Add additional mortgage analytics data
        result['mortgage_calculations'] = mortgage_data
        result['timestamp'] = timezone.now().isoformat()
        result['region'] = region
        
        return JsonResponse(result)
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in mortgage analytics: {e}")
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        logger.error(f"Error in mortgage analytics: {e}\n{traceback.format_exc()}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def mortgage_pdf_export(request):
    """
    PDF Export endpoint for mortgage analytics reports.
    
    POST /mortgage-analytics/pdf/
    Body: {
        "borrower_data": {
            "loan_amount": 300000,
            "interest_rate": 6.5,
            "term_years": 30,
            ...
        },
        "analysis_data": {
            "summary_markdown": "...",
            "structured_data": {...}
        }
    }
    
    Returns:
        PDF file download
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        # Import PDF generation utility
        from ..mortgage_report_utils import generate_mortgage_report_pdf
        
        data = json.loads(request.body)
        borrower_data = data.get('borrower_data', {})
        analysis_data = data.get('analysis_data', {})
        
        # Generate PDF
        pdf_buffer = generate_mortgage_report_pdf(borrower_data, analysis_data)
        
        # Create response with PDF content
        response = HttpResponse(
            pdf_buffer.getvalue(),
            content_type='application/pdf'
        )
        response['Content-Disposition'] = f'attachment; filename="Mortgage_Report_{datetime.now().strftime("%Y%m%d%H%M%S")}.pdf"'
        
        return response
        
    except ImportError as e:
        logger.error(f"PDF utility not available: {e}")
        return JsonResponse({'error': 'PDF generation not available'}, status=501)
    except Exception as e:
        logger.error(f"Error generating PDF: {e}\n{traceback.format_exc()}")
        return JsonResponse({'error': str(e)}, status=500)
