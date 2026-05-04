"""
EMI Calculator and Mortgage Views.
Contains endpoints for EMI calculations and mortgage-related operations.
"""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from .base import logger, calculate_emi

logger = logging.getLogger(__name__)


# =============================================================================
# EMI CALCULATOR API
# =============================================================================

@csrf_exempt
@require_POST
def emi_calculator_api(request):
    """
    EMI calculator API endpoint.
    
    POST /api/emi-calculator/
    Body: {
        "loan_amount": 500000,
        "interest_rate": 8.5,
        "tenure_months": 240,
        "method": "reducing_balance" (or "flat_rate"),
        "processing_fee": 1000
    }
    """
    try:
        data = json.loads(request.body)
        loan_amount = float(data.get('loan_amount', 0))
        interest_rate = float(data.get('interest_rate', 0))
        tenure_months = int(data.get('tenure_months', 0))
        method = data.get('method', 'reducing_balance')
        processing_fee = float(data.get('processing_fee', 0))
        
        if calculate_emi:
            result = calculate_emi(loan_amount, interest_rate, tenure_months, method, processing_fee)
        else:
            # Fallback calculation
            monthly_rate = interest_rate / 12 / 100
            emi = loan_amount * monthly_rate * (1 + monthly_rate) ** tenure_months / ((1 + monthly_rate) ** tenure_months - 1)
            result = {
                'monthly_emi': round(emi, 2),
                'total_interest': round(emi * tenure_months - loan_amount, 2)
            }
        
        return JsonResponse(result)
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# MORTGAGE CALCULATOR API
# =============================================================================

@csrf_exempt
@require_POST
def mortgage_calculator_api(request):
    """
    Mortgage calculator API endpoint.
    
    POST /api/mortgage-calculator/
    Body: {
        "loan_amount": 300000,
        "interest_rate": 6.5,
        "term_years": 30
    }
    """
    try:
        data = json.loads(request.body)
        loan_amount = float(data.get('loan_amount', 0))
        interest_rate = float(data.get('interest_rate', 0))
        term_years = int(data.get('term_years', 30))
        
        monthly_rate = interest_rate / 100 / 12
        num_payments = term_years * 12
        monthly_payment = loan_amount * monthly_rate * (1 + monthly_rate) ** num_payments / ((1 + monthly_rate) ** num_payments - 1)
        
        return JsonResponse({
            'monthly_payment': round(monthly_payment, 2),
            'total_payment': round(monthly_payment * num_payments, 2),
            'total_interest': round(monthly_payment * num_payments - loan_amount, 2)
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# LOAN APPLICATION API
# =============================================================================

@csrf_exempt
@require_POST
def loan_application_api(request):
    """
    Loan application API endpoint.
    
    POST /api/loan-application/
    Body: {
        "applicant_name": "John Doe",
        "loan_amount": 500000,
        "loan_purpose": "home"
    }
    """
    try:
        data = json.loads(request.body)
        
        # Generate application ID
        import time
        application_id = f'APP-{int(time.time() * 1000)}'
        
        return JsonResponse({
            'application_id': application_id,
            'status': 'submitted',
            'message': 'Loan application submitted successfully'
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
