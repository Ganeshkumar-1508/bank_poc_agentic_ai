"""
Loan Decision Views.
Contains endpoints for automated loan decisions using CrewAI.
"""

import json
import logging
import traceback

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .base import (
    logger,
    get_user_region_from_session,
)
from .crew_api_views import run_crew

logger = logging.getLogger(__name__)


# =============================================================================
# LOAN CREWAI DECISION API
# =============================================================================

@csrf_exempt
@require_POST
def loan_crewai_decision_api(request):
    """
    Submit loan for automated CrewAI decision.
    
    POST /api/loan-crewai-decision/
    Body: {
        'loan_id': int
    }
    
    Returns: {
        'success': bool,
        'decision': str (APPROVED, REJECTED, REQUIRES_REVIEW),
        'confidence': float,
        'auto_executed': bool,
        'new_status': str
    }
    """
    try:
        from .models import LoanApplication, AuditLog, CrewAIReasoningLog
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        
        data = json.loads(request.body)
        loan_id = data.get('loan_id')
        
        if not loan_id:
            return JsonResponse({'error': 'loan_id is required'}, status=400)
        
        loan = LoanApplication.objects.get(pk=loan_id)
        
        # Prepare borrower data for CrewAI
        borrower_json = json.dumps({
            'applicant_income': float(loan.applicant_income),
            'coapplicant_income': float(loan.coapplicant_income),
            'credit_score': float(loan.credit_score or 0),
            'dti_ratio': float(loan.dti_ratio),
            'loan_amount': float(loan.loan_amount),
            'loan_term': int(loan.loan_term_months),
            'collateral_value': float(loan.collateral_value),
            'savings': 0  # Add if available
        })
        
        logger.info(f"Running Credit Risk Crew for loan {loan.application_id}")

        # Get user region from session
        region_data = get_user_region_from_session(request)
        region = region_data.get("country_name", "India")

        # Call the generic run_crew endpoint
        class MockRequest:
            def __init__(self, data):
                self.body = json.dumps(data).encode()
                self.META = request.META

        mock_request = MockRequest({
            'crew_type': 'credit_risk',
            'query': borrower_json,
            'region': region
        })

        response = run_crew(mock_request)
        response_data = json.loads(response.content)
        raw_output = response_data.get('result', '')
        
        # Simple parsing - in production, use more robust NLP
        decision = 'REQUIRES_REVIEW'
        confidence = 50.0
        
        if 'APPROVED' in raw_output.upper() or 'APPROVAL' in raw_output.upper():
            decision = 'APPROVED'
            confidence = 85.0
        elif 'REJECTED' in raw_output.upper() or 'DENIED' in raw_output.upper():
            decision = 'REJECTED'
            confidence = 85.0
        elif 'HIGH RISK' in raw_output.upper():
            decision = 'REJECTED'
            confidence = 90.0
        elif 'LOW RISK' in raw_output.upper():
            decision = 'APPROVED'
            confidence = 80.0
        
        # Extract key factors from output
        factors = []
        if 'credit score' in raw_output.lower():
            factors.append('Credit Score Analysis')
        if 'dti' in raw_output.lower() or 'debt-to-income' in raw_output.lower():
            factors.append('DTI Ratio Assessment')
        if 'income' in raw_output.lower():
            factors.append('Income Verification')
        if 'collateral' in raw_output.lower():
            factors.append('Collateral Evaluation')
        
        # Log reasoning
        reasoning_log = CrewAIReasoningLog.objects.create(
            application=loan,
            crew_type='credit_risk',
            decision=decision,
            confidence_score=confidence,
            reasoning={'raw_output': raw_output[:5000]},  # Truncate for storage
            factors=factors,
            recommendations=[f'Auto-{decision.lower()} based on CrewAI analysis'],
            auto_executed=(confidence > 75)
        )
        
        # Auto-execute if confidence > 75%
        auto_executed = False
        if confidence > 75:
            if decision == 'APPROVED':
                loan.status = 'APPROVED'
                action = 'CREWAI_AUTO_APPROVED'
            else:
                loan.status = 'REJECTED'
                action = 'CREWAI_AUTO_REJECTED'
            
            loan.save()  # Triggers audit log
            auto_executed = True
            
            # Broadcast via WebSocket
            try:
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    'dashboard_updates',
                    {
                        'type': 'crewai_decision',
                        'loan_id': loan.id,
                        'decision': decision,
                        'confidence': confidence,
                        'reasoning': {'factors': factors}
                    }
                )
            except Exception as ws_error:
                logger.warning(f"WebSocket broadcast failed: {ws_error}")
        else:
            loan.status = 'UNDER_REVIEW'
            loan.save()
            action = 'CREWAI_REQUIRES_REVIEW'
        
        # Create audit entry
        AuditLog.objects.create(
            application=loan,
            action=action,
            actor_type='CREWAI',
            actor_id='credit_risk_crew',
            details={
                'confidence_score': confidence,
                'decision': decision,
                'factors': factors,
                'timestamp': timezone.now().isoformat()
            }
        )
        
        return JsonResponse({
            'success': True,
            'decision': decision,
            'confidence': confidence,
            'auto_executed': auto_executed,
            'new_status': loan.status,
            'factors': factors,
            'reasoning_log_id': reasoning_log.id
        })
    
    except LoanApplication.DoesNotExist:
        return JsonResponse({'error': 'Loan not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"CrewAI decision error: {e}")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
