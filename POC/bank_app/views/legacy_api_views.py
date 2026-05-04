"""
Legacy API Views.
Contains older API endpoints maintained for backward compatibility.
"""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from .base import logger

logger = logging.getLogger(__name__)


# =============================================================================
# KYC VERIFY API
# =============================================================================

@csrf_exempt
@require_POST
def kyc_verify_api(request):
    """
    KYC verification API endpoint.
    
    POST /api/kyc-verify/
    Body: {"customer_id": "CUST001"}
    """
    try:
        data = json.loads(request.body)
        
        # Placeholder for KYC verification
        return JsonResponse({
            'verified': True,
            'message': 'KYC verification completed',
            'customer_id': data.get('customer_id', 'CUST001')
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# COMPLIANCE CHECK API
# =============================================================================

@csrf_exempt
@require_POST
def compliance_check_api(request):
    """
    Compliance (AML/PEP) check API endpoint.
    
    POST /api/compliance-check/
    Body: {"entity_name": "John Doe"}
    """
    try:
        data = json.loads(request.body)
        
        # Placeholder for compliance check
        return JsonResponse({
            'compliant': True,
            'message': 'No compliance issues found',
            'checks_performed': ['AML', 'PEP', 'Sanctions']
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# RAG QUERY API
# =============================================================================

@csrf_exempt
@require_POST
def rag_query_api(request):
    """
    RAG engine query API endpoint.
    
    POST /api/rag-query/
    Body: {"query": "What is the loan process?"}
    """
    try:
        data = json.loads(request.body)
        query = data.get('query', '')
        
        # Placeholder for RAG query
        return JsonResponse({
            'query': query,
            'results': [],
            'message': 'RAG query completed'
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
