"""
RESTful API Views for Loan Applications and Dashboard
"""

import json
import logging
from datetime import datetime
from decimal import Decimal

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Sum
from django.utils import timezone

from .models import LoanApplication, AuditLog, CrewAIReasoningLog

logger = logging.getLogger(__name__)


# =============================================================================
# LOAN APPLICATION CRUD ENDPOINTS
# =============================================================================

@csrf_exempt
@require_http_methods(["GET"])
def loan_list_api(request):
    """
    List all loan applications with optional filtering.
    
    Query Parameters:
    - status: Filter by status (e.g., SUBMITTED, APPROVED)
    - region: Filter by region (IN, US)
    - search: Search by applicant name or application ID
    
    Returns:
    {
        'loans': [...],
        'count': int,
        'filters': {...}
    }
    """
    try:
        status = request.GET.get('status')
        region = request.GET.get('region')
        search = request.GET.get('search')
        
        queryset = LoanApplication.objects.all()
        
        if status:
            queryset = queryset.filter(status=status)
        if region:
            queryset = queryset.filter(region=region)
        if search:
            queryset = queryset.filter(
                Q(applicant_name__icontains=search) |
                Q(application_id__icontains=search)
            )
        
        loans = [{
            'id': loan.id,
            'application_id': loan.application_id,
            'status': loan.status,
            'applicant_name': loan.applicant_name,
            'applicant_email': loan.applicant_email,
            'loan_amount': str(loan.loan_amount),
            'loan_term_months': loan.loan_term_months,
            'credit_score': loan.credit_score,
            'region': loan.region,
            'created_at': loan.created_at.isoformat(),
            'submitted_at': loan.submitted_at.isoformat() if loan.submitted_at else None
        } for loan in queryset[:100]]  # Limit to 100 for performance
        
        return JsonResponse({
            'loans': loans,
            'count': len(loans),
            'total_count': queryset.count(),
            'filters': {
                'status': status,
                'region': region,
                'search': search
            }
        })
        
    except Exception as e:
        logger.error(f"Loan list API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def loan_create_api(request):
    """
    Create a new loan application.
    
    Body:
    {
        'applicant_name': str,
        'applicant_email': str (optional),
        'applicant_income': float,
        'loan_amount': float,
        'loan_term_months': int,
        'loan_purpose': str (optional),
        'credit_score': int (optional),
        'region': str (default: IN)
    }
    
    Returns:
    {
        'success': bool,
        'application_id': str,
        'loan_id': int
    }
    """
    try:
        data = json.loads(request.body)
        
        # Required fields
        required_fields = ['applicant_name', 'applicant_income', 'loan_amount', 'loan_term_months']
        for field in required_fields:
            if field not in data:
                return JsonResponse({'error': f'{field} is required'}, status=400)
        
        loan = LoanApplication.objects.create(
            applicant_name=data['applicant_name'],
            applicant_email=data.get('applicant_email'),
            applicant_income=Decimal(str(data['applicant_income'])),
            coapplicant_income=Decimal(str(data.get('coapplicant_income', 0))),
            loan_amount=Decimal(str(data['loan_amount'])),
            loan_term_months=int(data['loan_term_months']),
            loan_purpose=data.get('loan_purpose'),
            credit_score=int(data.get('credit_score')) if data.get('credit_score') else None,
            dti_ratio=Decimal(str(data.get('dti_ratio', 0))),
            region=data.get('region', 'IN'),
            status='DRAFT'
        )
        
        # Create initial audit log
        AuditLog.objects.create(
            application=loan,
            action='LOAN_UPDATED',
            actor_type='USER',
            actor_id='anonymous',
            details={
                'action': 'created',
                'timestamp': timezone.now().isoformat()
            }
        )
        
        return JsonResponse({
            'success': True,
            'application_id': loan.application_id,
            'loan_id': loan.id,
            'status': loan.status
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Loan create API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def loan_detail_api(request, loan_id):
    """
    Get loan application details by ID.
    
    Returns:
    {
        'loan': {...},
        'audit_logs': [...],
        'crewai_decisions': [...]
    }
    """
    try:
        loan = LoanApplication.objects.get(pk=loan_id)
        
        loan_data = {
            'id': loan.id,
            'application_id': loan.application_id,
            'status': loan.status,
            'region': loan.region,
            'applicant_name': loan.applicant_name,
            'applicant_email': loan.applicant_email,
            'applicant_phone': loan.applicant_phone,
            'date_of_birth': loan.date_of_birth.isoformat() if loan.date_of_birth else None,
            'pan_number': loan.pan_number,
            'ssn_last_4': loan.ssn_last_4,
            'applicant_income': str(loan.applicant_income),
            'coapplicant_income': str(loan.coapplicant_income),
            'employment_status': loan.employment_status,
            'employment_years': loan.employment_years,
            'loan_amount': str(loan.loan_amount),
            'loan_term_months': loan.loan_term_months,
            'loan_purpose': loan.loan_purpose,
            'credit_score': loan.credit_score,
            'dti_ratio': str(loan.dti_ratio),
            'existing_loans': str(loan.existing_loans),
            'collateral_value': str(loan.collateral_value),
            'collateral_type': loan.collateral_type,
            'risk_assessment': loan.risk_assessment,
            'approval_probability': str(loan.approval_probability),
            'risk_grade': loan.risk_grade,
            'kyc_status': loan.kyc_status,
            'kyc_data': loan.kyc_data,
            'compliance_status': loan.compliance_status,
            'compliance_results': loan.compliance_results,
            'created_at': loan.created_at.isoformat(),
            'updated_at': loan.updated_at.isoformat(),
            'submitted_at': loan.submitted_at.isoformat() if loan.submitted_at else None,
            'decided_at': loan.decided_at.isoformat() if loan.decided_at else None
        }
        
        # Get audit logs
        audit_logs = [{
            'id': log.id,
            'action': log.action,
            'actor_type': log.actor_type,
            'actor_id': log.actor_id,
            'details': log.details,
            'ip_address': log.ip_address,
            'created_at': log.created_at.isoformat()
        } for log in loan.audit_logs.all()[:50]]
        
        # Get CrewAI decisions
        crewai_decisions = [{
            'id': log.id,
            'crew_type': log.crew_type,
            'decision': log.decision,
            'confidence_score': str(log.confidence_score),
            'reasoning': log.reasoning,
            'factors': log.factors,
            'auto_executed': log.auto_executed,
            'executed_at': log.executed_at.isoformat()
        } for log in loan.crewai_reasoning_logs.all()[:20]]
        
        return JsonResponse({
            'loan': loan_data,
            'audit_logs': audit_logs,
            'crewai_decisions': crewai_decisions
        })
        
    except LoanApplication.DoesNotExist:
        return JsonResponse({'error': 'Loan not found'}, status=404)
    except Exception as e:
        logger.error(f"Loan detail API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def loan_update_api(request, loan_id):
    """
    Update loan application.
    
    Body:
    {
        'applicant_name': str (optional),
        'loan_amount': float (optional),
        ... any field ...
    }
    
    Returns:
    {
        'success': bool,
        'loan_id': int
    }
    """
    try:
        loan = LoanApplication.objects.get(pk=loan_id)
        data = json.loads(request.body)
        
        # Update fields
        for key, value in data.items():
            if hasattr(loan, key) and key not in ['id', 'application_id', 'created_at', 'updated_at']:
                if isinstance(getattr(loan, key), Decimal) and value is not None:
                    value = Decimal(str(value))
                elif isinstance(getattr(loan, key), int) and value is not None:
                    value = int(value)
                setattr(loan, key, value)
        
        loan.save()
        
        return JsonResponse({
            'success': True,
            'loan_id': loan.id,
            'application_id': loan.application_id
        })
        
    except LoanApplication.DoesNotExist:
        return JsonResponse({'error': 'Loan not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Loan update API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def loan_delete_api(request, loan_id):
    """
    Delete loan application (soft delete by setting status to DRAFT).
    """
    try:
        loan = LoanApplication.objects.get(pk=loan_id)
        
        # Soft delete: set to DRAFT status
        loan.status = 'DRAFT'
        loan.save()
        
        AuditLog.objects.create(
            application=loan,
            action='LOAN_UPDATED',
            actor_type='USER',
            actor_id='anonymous',
            details={
                'action': 'deleted',
                'timestamp': timezone.now().isoformat()
            }
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Loan application deleted'
        })
        
    except LoanApplication.DoesNotExist:
        return JsonResponse({'error': 'Loan not found'}, status=404)
    except Exception as e:
        logger.error(f"Loan delete API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# LOAN STATUS UPDATE ENDPOINTS
# =============================================================================

@csrf_exempt
@require_POST
def loan_submit_api(request, loan_id):
    """Submit loan for review."""
    try:
        loan = LoanApplication.objects.get(pk=loan_id)
        loan.status = 'SUBMITTED'
        loan.save()
        
        return JsonResponse({
            'success': True,
            'status': loan.status,
            'application_id': loan.application_id
        })
        
    except LoanApplication.DoesNotExist:
        return JsonResponse({'error': 'Loan not found'}, status=404)
    except Exception as e:
        logger.error(f"Loan submit API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def loan_approve_api(request, loan_id):
    """Approve loan application."""
    try:
        loan = LoanApplication.objects.get(pk=loan_id)
        loan.status = 'APPROVED'
        loan.save()
        
        return JsonResponse({
            'success': True,
            'status': loan.status,
            'application_id': loan.application_id
        })
        
    except LoanApplication.DoesNotExist:
        return JsonResponse({'error': 'Loan not found'}, status=404)
    except Exception as e:
        logger.error(f"Loan approve API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def loan_reject_api(request, loan_id):
    """Reject loan application."""
    try:
        loan = LoanApplication.objects.get(pk=loan_id)
        loan.status = 'REJECTED'
        loan.save()
        
        return JsonResponse({
            'success': True,
            'status': loan.status,
            'application_id': loan.application_id
        })
        
    except LoanApplication.DoesNotExist:
        return JsonResponse({'error': 'Loan not found'}, status=404)
    except Exception as e:
        logger.error(f"Loan reject API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# BULK OPERATIONS ENDPOINTS
# =============================================================================

@csrf_exempt
@require_POST
def bulk_loan_approve_api(request):
    """
    Bulk approve loan applications.
    
    Body (preview mode):
    {
        'loan_ids': [1, 2, 3] OR
        'filter_criteria': {'status': 'SUBMITTED', 'region': 'IN'},
        'confirm': false
    }
    
    Body (confirm mode):
    {
        'loan_ids': [1, 2, 3] OR
        'filter_criteria': {...},
        'confirm': true
    }
    
    Returns (preview):
    {
        'preview': {
            'count': int,
            'loans': [...],
            'warnings': [...]
        }
    }
    
    Returns (confirm):
    {
        'success': bool,
        'approved_count': int,
        'total_count': int
    }
    """
    try:
        data = json.loads(request.body)
        loan_ids = data.get('loan_ids', [])
        filter_criteria = data.get('filter_criteria')
        confirm = data.get('confirm', False)
        
        # Get loans to process
        if filter_criteria:
            queryset = LoanApplication.objects.filter(**filter_criteria)
        else:
            queryset = LoanApplication.objects.filter(id__in=loan_ids)
        
        loans = list(queryset)
        
        if not confirm:
            # Return preview summary
            preview = {
                'count': len(loans),
                'loans': [{
                    'id': loan.id,
                    'application_id': loan.application_id,
                    'current_status': loan.status,
                    'applicant_name': loan.applicant_name,
                    'loan_amount': str(loan.loan_amount)
                } for loan in loans],
                'warnings': [
                    loan.application_id for loan in loans 
                    if loan.status not in ['SUBMITTED', 'UNDER_REVIEW']
                ]
            }
            return JsonResponse({'preview': preview})
        
        # Execute bulk approval
        approved_count = 0
        for loan in loans:
            if loan.status in ['SUBMITTED', 'UNDER_REVIEW']:
                loan.status = 'APPROVED'
                loan.save()  # Triggers individual audit entry
                approved_count += 1
        
        # Broadcast via WebSocket
        _broadcast_admin_action('BULK_APPROVE', [loan.id for loan in loans])
        
        return JsonResponse({
            'success': True,
            'approved_count': approved_count,
            'total_count': len(loans)
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Bulk approve API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def bulk_loan_reject_api(request):
    """
    Bulk reject loan applications (same structure as bulk_approve).
    """
    try:
        data = json.loads(request.body)
        loan_ids = data.get('loan_ids', [])
        filter_criteria = data.get('filter_criteria')
        confirm = data.get('confirm', False)
        
        if filter_criteria:
            queryset = LoanApplication.objects.filter(**filter_criteria)
        else:
            queryset = LoanApplication.objects.filter(id__in=loan_ids)
        
        loans = list(queryset)
        
        if not confirm:
            preview = {
                'count': len(loans),
                'loans': [{
                    'id': loan.id,
                    'application_id': loan.application_id,
                    'current_status': loan.status,
                    'applicant_name': loan.applicant_name
                } for loan in loans],
                'warnings': [
                    loan.application_id for loan in loans 
                    if loan.status not in ['SUBMITTED', 'UNDER_REVIEW']
                ]
            }
            return JsonResponse({'preview': preview})
        
        rejected_count = 0
        for loan in loans:
            if loan.status in ['SUBMITTED', 'UNDER_REVIEW']:
                loan.status = 'REJECTED'
                loan.save()
                rejected_count += 1
        
        _broadcast_admin_action('BULK_REJECT', [loan.id for loan in loans])
        
        return JsonResponse({
            'success': True,
            'rejected_count': rejected_count,
            'total_count': len(loans)
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Bulk reject API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# DASHBOARD DATA ENDPOINTS
# =============================================================================

@csrf_exempt
@require_http_methods(["GET"])
def dashboard_stats_api(request):
    """
    Get dashboard statistics.
    
    Returns:
    {
        'total_loans': int,
        'by_status': {...},
        'total_amount': str,
        'pending_approvals': int,
        'recent_loans': [...]
    }
    """
    try:
        # Total loans
        total_loans = LoanApplication.objects.count()
        
        # By status
        by_status = {}
        for status, label in LoanApplication.STATUS_CHOICES:
            count = LoanApplication.objects.filter(status=status).count()
            by_status[status] = {'count': count, 'label': label}
        
        # Total loan amount
        total_amount = LoanApplication.objects.aggregate(
            total=Sum('loan_amount')
        )['total'] or Decimal('0')
        
        # Pending approvals
        pending_approvals = LoanApplication.objects.filter(
            status__in=['SUBMITTED', 'UNDER_REVIEW']
        ).count()
        
        # Recent loans
        recent_loans = [{
            'id': loan.id,
            'application_id': loan.application_id,
            'applicant_name': loan.applicant_name,
            'loan_amount': str(loan.loan_amount),
            'status': loan.status,
            'created_at': loan.created_at.isoformat()
        } for loan in LoanApplication.objects.all()[:10]]
        
        return JsonResponse({
            'total_loans': total_loans,
            'by_status': by_status,
            'total_amount': str(total_amount),
            'pending_approvals': pending_approvals,
            'recent_loans': recent_loans
        })
        
    except Exception as e:
        logger.error(f"Dashboard stats API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def dashboard_charts_api(request):
    """
    Get chart data for dashboard visualizations.
    
    Returns:
    {
        'status_distribution': [...],
        'monthly_trend': [...],
        'region_performance': [...]
    }
    """
    try:
        # Status distribution
        status_data = []
        for status, label in LoanApplication.STATUS_CHOICES:
            count = LoanApplication.objects.filter(status=status).count()
            if count > 0:
                status_data.append({'status': status, 'label': label, 'count': count})
        
        # Monthly trend (loans created per month)
        from django.db.models import TruncMonth
        monthly = LoanApplication.objects.annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            count=Count('id')
        ).order_by('month')
        
        monthly_trend = [{
            'month': m['month'].isoformat(),
            'count': m['count']
        } for m in monthly]
        
        # Region performance
        region_data = []
        for region, label in LoanApplication.REGION_CHOICES:
            total = LoanApplication.objects.filter(region=region).count()
            approved = LoanApplication.objects.filter(region=region, status='APPROVED').count()
            if total > 0:
                region_data.append({
                    'region': region,
                    'label': label,
                    'total': total,
                    'approved': approved,
                    'approval_rate': round(approved / total * 100, 2) if total > 0 else 0
                })
        
        return JsonResponse({
            'status_distribution': status_data,
            'monthly_trend': monthly_trend,
            'region_performance': region_data
        })
        
    except Exception as e:
        logger.error(f"Dashboard charts API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)
    
    
    # =============================================================================
    # COUNTRY LIST API
    # =============================================================================
    
    @csrf_exempt
    @require_http_methods(["GET"])
    def country_list_api(request):
        """
        Get list of all available countries with flag and currency info.
        
        GET /api/country-list/
        Returns: List of countries with code, name, flag, currency
        
        Example Response:
        {
            'countries': [
                {'code': 'IN', 'name': 'India', 'flag': '🇮🇳', 'currency': '₹'},
                {'code': 'US', 'name': 'United States', 'flag': '🇺🇸', 'currency': '$'}
            ]
        }
        """
        try:
            from .views.base import get_all_countries
            
            all_countries = get_all_countries()
            countries = []
            
            for code, info in sorted(all_countries.items(), key=lambda x: x[1].get('name', '')):
                countries.append({
                    'code': code,
                    'name': info.get('name', code),
                    'flag': info.get('flag', '🌐'),
                    'currency': info.get('currency', '$'),
                    'currency_code': info.get('currency_code', '')
                })
            
            return JsonResponse({'countries': countries})
            
        except Exception as e:
            logger.error(f"Country list API error: {e}")
            return JsonResponse({'error': str(e)}, status=500)
    
    
    # =============================================================================
    # HELPER FUNCTIONS
    # =============================================================================

def _broadcast_admin_action(action, affected_loans):
    """Broadcast admin action via WebSocket."""
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'dashboard_updates',
            {
                'type': 'admin_action',
                'action': action,
                'affected_loans': affected_loans,
                'timestamp': timezone.now().isoformat()
            }
        )
    except Exception as e:
        logger.warning(f"WebSocket broadcast failed: {e}")
