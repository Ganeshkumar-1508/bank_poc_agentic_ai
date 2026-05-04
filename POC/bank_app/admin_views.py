"""
Admin Panel Views for Bank POC Agentic AI
Uses direct SQLite queries to legacy database (Test/tools/bank_poc.db)
Framework-agnostic design for easy migration to Flask/FastAPI
"""
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from datetime import datetime, timedelta
import logging

# Import legacy database utilities
from .db_utils import (
    get_table_counts,
    get_all_records,
    get_record_by_id,
    count_records,
    create_record,
    update_record,
    delete_record,
    execute_raw_sql,
    get_loan_applications,
    get_fixed_deposits,
    get_users,
    get_transactions,
    LEGACY_DB_PATH,
)
from utils.geolocation import get_all_countries

logger = logging.getLogger(__name__)


# =============================================================================
# ADMIN AUTHENTICATION (Simple - can be enhanced with proper auth)
# =============================================================================

def admin_login_required(view_func):
    """Decorator to require admin login using Django session."""
    def wrapper(request, *args, **kwargs):
        if not request.session.get('admin_logged_in'):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Unauthorized'}, status=401)
            return redirect('admin_panel:admin_login')
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_login(request):
    """Secure admin login using Django authentication with legacy DB support."""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # Try Django's auth first (requires createsuperuser)
        user = authenticate(request, username=username, password=password)
        
        if user is not None and user.is_staff:
            login(request, user)
            request.session['admin_logged_in'] = True
            request.session['admin_username'] = user.username
            request.session.set_expiry(3600)  # 1 hour timeout
            return redirect('admin_panel:admin_dashboard')
        
        # Fallback: Check legacy admin credentials from database
        # This allows admin access without Django superuser setup
        admin_user = execute_raw_sql(
            "SELECT username, password_hash FROM auth_user WHERE is_staff = 1 AND username = ?",
            (username,),
            fetch="one"
        )
        
        # For development: simple password check (replace with proper hashing in production)
        # In production, use Django's password hashing
        if admin_user:
            # This is a simplified check - use Django's check_password() in production
            from django.contrib.auth.models import User
            try:
                django_user = User.objects.get(username=username)
                if django_user.check_password(password):
                    login(request, django_user)
                    request.session['admin_logged_in'] = True
                    request.session['admin_username'] = username
                    request.session.set_expiry(3600)
                    return redirect('admin_panel:admin_dashboard')
            except:
                pass
        
        return render(request, 'bank_app/admin/admin_login.html', {
            'error': 'Invalid credentials or insufficient permissions'
        })
    return render(request, 'bank_app/admin/admin_login.html')


def admin_logout(request):
    """Secure logout using Django's logout."""
    logout(request)
    request.session.flush()
    return redirect('admin_panel:admin_login')


# =============================================================================
# DASHBOARD
# =============================================================================

@admin_login_required
def admin_dashboard(request):
    """Admin dashboard with key metrics from legacy database."""
    now = timezone.now()
    today = now.date()
    yesterday = now - timedelta(days=1)

    # Total users from legacy users table
    total_users = count_records('users')

    # Active sessions - count users with recent activity (using created_at as proxy)
    active_sessions = count_records('users', "created_at >= ?", (yesterday.isoformat(),))

    # New users today
    new_users_today = count_records('users', "DATE(created_at) = DATE(?)", (today.isoformat(),))

    # Pending reviews - loan applications without decision
    pending_reviews = count_records('loan_applications', "loan_decision = 'NEEDS_VERIFY' OR loan_decision = '' OR loan_decision IS NULL")

    # Approved loans today
    approved_today = count_records('loan_applications', "loan_decision = 'APPROVED' AND DATE(created_at) = DATE(?)", (today.isoformat(),))

    # Recent activity from compliance_audit_log (not loan_applications)
    recent_logs = get_all_records('compliance_audit_log', order_by='logged_at DESC', limit=10)

    # Add computed fields for template compatibility
    for log in recent_logs:
        log['action'] = log.get('event_type', 'UNKNOWN')
        log['details'] = log.get('event_detail', '')

    # Regional distribution - using country_code from address table joined with users
    regional_data = execute_raw_sql("""
        SELECT a.country_code, COUNT(*) as count
        FROM users u
        LEFT JOIN address a ON u.user_id = a.user_id
        GROUP BY a.country_code
        ORDER BY count DESC
        LIMIT 6
    """, fetch="all")

    regional_distribution = []
    all_countries = get_all_countries()
    if regional_data:
        for item in regional_data:
            country_code = item.get('country_code', '')
            if country_code:
                country_name = all_countries.get(country_code, {}).get('name', country_code)
                regional_distribution.append((country_name, item['count']))

    context = {
        'total_users': total_users,
        'active_sessions': active_sessions,
        'new_users_today': new_users_today,
        'pending_reviews': pending_reviews,
        'approved_today': approved_today,
        'recent_logs': recent_logs,
        'regional_distribution': regional_distribution,
    }

    return render(request, 'bank_app/admin/admin_dashboard.html', context)


# =============================================================================
# USER MANAGEMENT
# =============================================================================

@admin_login_required
def admin_user_list(request):
    """List all user sessions with search and filter."""
    from bank_app.models import UserSession
    
    search = request.GET.get('search', '')
    country = request.GET.get('country', '')
    is_active = request.GET.get('is_active', '')
    
    # Build query based on filters
    sessions = UserSession.objects.all()
    
    if search:
        sessions = sessions.filter(
            session_id__icontains=search
        ) | sessions.filter(
            city__icontains=search
        ) | sessions.filter(
            country_name__icontains=search
        )
    
    if country:
        sessions = sessions.filter(country_code=country)
    
    if is_active:
        is_active_bool = is_active.lower() == 'true'
        sessions = sessions.filter(is_active=is_active_bool)
    
    sessions = sessions.order_by('-last_activity')
    
    context = {
        'users': sessions,
        'search': search,
        'country': country,
        'is_active': is_active,
        'countries': list(get_all_countries().keys()),
    }
    
    return render(request, 'bank_app/admin/admin_user_list.html', context)


@admin_login_required
def admin_user_detail(request, session_id):
    """View user session details."""
    from bank_app.models import UserSession
    
    session = UserSession.objects.filter(session_id=session_id).first()
    
    if not session:
        return redirect('admin_panel:admin_user_list')
    
    context = {
        'user': session,
        'address': None,
        'accounts': [],
        'loans': [],
        'fds': [],
    }
    
    return render(request, 'bank_app/admin/admin_user_detail.html', context)


@admin_login_required
@require_POST
def admin_toggle_user_active(request, session_id):
    """Toggle user session active status."""
    from bank_app.models import UserSession
    
    session = UserSession.objects.filter(session_id=session_id).first()
    
    if not session:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
    
    session.is_active = not session.is_active
    session.save()
    
    return JsonResponse({
        'success': True,
        'session_id': session_id,
        'is_active': session.is_active
    })


# =============================================================================
# TRANSACTION MONITORING (Loans and FDs)
# =============================================================================

@admin_login_required
def admin_transaction_list(request):
    """List all transactions (loans and FDs) with filtering."""
    type_filter = request.GET.get('type', 'all')
    status_filter = request.GET.get('status', 'all')
    search = request.GET.get('search', '')

    # Whitelist for safe status values to prevent SQL injection
    ALLOWED_LOAN_STATUSES = ['APPROVED', 'REJECTED', 'NEEDS_VERIFY', '']
    ALLOWED_FD_STATUSES = ['ACTIVE', 'MATURED', 'CLOSED', 'PREMATURE', '']

    loans = []
    fds = []

    if type_filter in ['loan', 'all']:
        # Build loan query with parameterized WHERE clause
        conditions = []
        params = []

        # Validate status_filter against whitelist
        if status_filter != 'all' and status_filter and status_filter in ALLOWED_LOAN_STATUSES:
            conditions.append("loan_decision = ?")
            params.append(status_filter)

        if search:
            conditions.append("(application_id LIKE ? OR applicant_email LIKE ?)")
            search_param = f"%{search}%"
            params.extend([search_param, search_param])

        # Build WHERE clause safely
        where_clause = " AND ".join(conditions) if conditions else ""
        query = "SELECT * FROM loan_applications"
        if where_clause:
            query += f" WHERE {where_clause}"
        query += " ORDER BY created_at DESC LIMIT 50"

        loans = execute_raw_sql(query, tuple(params), fetch="all")

        # Add computed fields for template compatibility
        for loan in loans:
            loan['status'] = loan.get('loan_decision', 'NEEDS_VERIFY')
            loan['loan_amount'] = loan.get('loan_amnt', 0)

    if type_filter in ['fd', 'all']:
        # FDs are in fixed_deposit table
        conditions = []
        params = []

        # Validate status_filter against whitelist
        if status_filter != 'all' and status_filter and status_filter in ALLOWED_FD_STATUSES:
            conditions.append("fd_status = ?")
            params.append(status_filter)

        if search:
            conditions.append("(user_id LIKE ? OR bank_name LIKE ?)")
            search_param = f"%{search}%"
            params.extend([search_param, search_param])

        where_clause = " AND ".join(conditions) if conditions else ""
        query = "SELECT * FROM fixed_deposit"
        if where_clause:
            query += f" WHERE {where_clause}"
        query += " ORDER BY created_at DESC LIMIT 50"

        fds = execute_raw_sql(query, tuple(params), fetch="all")

    context = {
        'loans': loans,
        'fds': fds,
        'type_filter': type_filter,
        'status_filter': status_filter,
        'search': search,
        'status_choices': [
            ('NEEDS_VERIFY', 'Needs Verification'),
            ('APPROVED', 'Approved'),
            ('REJECTED', 'Rejected'),
        ],
    }

    return render(request, 'bank_app/admin/admin_transactions.html', context)


@admin_login_required
def admin_transaction_detail(request, application_id):
    """View loan application details."""
    application = get_record_by_id('loan_applications', application_id)
    
    if not application:
        return redirect('admin_panel:admin_transaction_list')
    
    # Get related disbursements
    disbursements = get_all_records(
        'loan_disbursements',
        "application_id = ?",
        (application_id,),
        order_by='created_at DESC'
    )
    
    # Get user details
    user_id = application.get('user_id')
    user = get_record_by_id('users', user_id) if user_id else None
    
    context = {
        'application': application,
        'disbursements': disbursements,
        'user': user,
    }
    
    return render(request, 'bank_app/admin/admin_transaction_detail.html', context)


@admin_login_required
@require_POST
def admin_approve_transaction(request, application_id):
    """Approve a loan application."""
    application = get_record_by_id('loan_applications', application_id)
    
    if not application:
        return JsonResponse({'success': False, 'error': 'Application not found'}, status=404)
    
    # Update loan decision
    success = update_record('loan_applications', application_id, {
        'loan_decision': 'APPROVED',
        'updated_at': timezone.now().isoformat(),
    })
    
    return JsonResponse({
        'success': success,
        'application_id': application_id,
        'new_status': 'APPROVED'
    })


@admin_login_required
@require_POST
def admin_reject_transaction(request, application_id):
    """Reject a loan application."""
    application = get_record_by_id('loan_applications', application_id)
    
    if not application:
        return JsonResponse({'success': False, 'error': 'Application not found'}, status=404)
    
    # Update loan decision
    success = update_record('loan_applications', application_id, {
        'loan_decision': 'REJECTED',
        'updated_at': timezone.now().isoformat(),
    })
    
    return JsonResponse({
        'success': success,
        'application_id': application_id,
        'new_status': 'REJECTED'
    })


# =============================================================================
# ANALYTICS
# =============================================================================

@admin_login_required
def admin_analytics(request):
    """Analytics dashboard with detailed metrics from legacy database."""
    now = timezone.now()
    last_7_days = now - timedelta(days=7)
    last_30_days = now - timedelta(days=30)

    # Loan statistics
    total_loans = count_records('loan_applications')
    loans_last_7_days = count_records(
        'loan_applications',
        "DATE(created_at) >= DATE(?)",
        (last_7_days.isoformat(),)
    )
    loans_last_30_days = count_records(
        'loan_applications',
        "DATE(created_at) >= DATE(?)",
        (last_30_days.isoformat(),)
    )

    # Approval rate
    approved = count_records('loan_applications', "loan_decision = 'APPROVED'")
    approval_rate = (approved / total_loans * 100) if total_loans > 0 else 0

    # Status breakdown - use loan_decision directly
    status_breakdown = execute_raw_sql("""
        SELECT loan_decision, COUNT(*) as count
        FROM loan_applications
        GROUP BY loan_decision
    """, fetch="all")

    # Regional breakdown - format for template
    regional_loans_raw = execute_raw_sql("""
        SELECT a.country_code, COUNT(*) as count
        FROM loan_applications la
        LEFT JOIN users u ON la.user_id = u.user_id
        LEFT JOIN address a ON u.user_id = a.user_id
        GROUP BY a.country_code
        ORDER BY count DESC
    """, fetch="all")

    # Convert to template-friendly format with country names
    all_countries = get_all_countries()
    regional_loans = []
    for region in regional_loans_raw:
        country_code = region.get('country_code', '')
        country_name = all_countries.get(country_code, {}).get('name', country_code) if country_code else 'Unknown'
        regional_loans.append({
            'country_code': country_code,
            'region': country_name,
            'count': region['count']
        })

    # FD statistics
    total_fds = count_records('fixed_deposit')
    fds_last_7_days = count_records(
        'fixed_deposit',
        "DATE(created_at) >= DATE(?)",
        (last_7_days.isoformat(),)
    )

    # FD status breakdown
    fd_status_breakdown = execute_raw_sql("""
        SELECT fd_status, COUNT(*) as count
        FROM fixed_deposit
        GROUP BY fd_status
    """, fetch="all")

    context = {
        'total_loans': total_loans,
        'loans_last_7_days': loans_last_7_days,
        'loans_last_30_days': loans_last_30_days,
        'approval_rate': round(approval_rate, 1),
        'status_breakdown': status_breakdown,
        'regional_loans': regional_loans,
        'total_fds': total_fds,
        'fds_last_7_days': fds_last_7_days,
        'fd_status_breakdown': fd_status_breakdown,
    }

    return render(request, 'bank_app/admin/admin_analytics.html', context)


# =============================================================================
# CONFIGURATION
# =============================================================================

@admin_login_required
def admin_config(request):
    """Configuration management page - FD rates from legacy database."""
    # Get FD rates from interest_rates_catalog
    fd_rates = get_all_records('interest_rates_catalog', "is_active = 1", order_by='effective_date DESC')
    
    countries = list(get_all_countries().items())
    
    context = {
        'fd_rates': fd_rates,
        'countries': countries,
    }
    
    return render(request, 'bank_app/admin/admin_config.html', context)


@admin_login_required
@require_POST
def admin_update_config(request):
    """Update configuration settings (FD rates)."""
    config_type = request.POST.get('config_type')
    
    try:
        if config_type == 'fd_rates':
            rate_id = request.POST.get('rate_id')
            bank_name = request.POST.get('bank_name', '')
            rate = float(request.POST.get('rate', 0))
            tenure_min = int(request.POST.get('tenure_min', 0))
            tenure_max = int(request.POST.get('tenure_max', 0))
            general_rate = float(request.POST.get('general_rate', 0))
            senior_rate = float(request.POST.get('senior_rate', 0))
            country_code = request.POST.get('country_code', 'IN')
            is_active = request.POST.get('is_active', 'on') == 'on'
            
            if rate_id:
                # Update existing rate
                success = update_record('interest_rates_catalog', rate_id, {
                    'bank_name': bank_name,
                    'general_rate': general_rate,
                    'senior_rate': senior_rate,
                    'tenure_min_months': tenure_min,
                    'tenure_max_months': tenure_max,
                    'country_code': country_code,
                    'is_active': 1 if is_active else 0,
                })
                return JsonResponse({'success': success, 'message': 'FD rate updated successfully'})
            else:
                # Create new rate
                result = create_record('interest_rates_catalog', {
                    'bank_name': bank_name,
                    'product_type': 'FIXED_DEPOSIT',
                    'tenure_min_months': tenure_min,
                    'tenure_max_months': tenure_max,
                    'general_rate': general_rate,
                    'senior_rate': senior_rate,
                    'country_code': country_code,
                    'effective_date': timezone.now().date().isoformat(),
                    'is_active': 1 if is_active else 0,
                })
                return JsonResponse({'success': result is not None, 'message': 'FD rate added successfully'})
        
        return JsonResponse({'success': True, 'message': 'Configuration updated'})
    
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


# =============================================================================
# FIXED DEPOSIT MANAGEMENT
# =============================================================================

@admin_login_required
def admin_fd_list(request):
    """List all fixed deposits."""
    status_filter = request.GET.get('status', 'all')
    search = request.GET.get('search', '')
    
    conditions = []
    params = []
    
    if status_filter != 'all' and status_filter:
        conditions.append("fd_status = ?")
        params.append(status_filter)
    
    if search:
        conditions.append("(user_id LIKE ? OR bank_name LIKE ?)")
        search_param = f"%{search}%"
        params.extend([search_param, search_param])
    
    where_clause = ""
    if conditions:
        where_clause = " AND ".join(conditions)
    
    fds = execute_raw_sql(f"""
        SELECT fd.*, u.email as user_email, u.first_name, u.last_name
        FROM fixed_deposit fd
        LEFT JOIN users u ON fd.user_id = u.user_id
        {f'WHERE {where_clause}' if where_clause else ''}
        ORDER BY fd.created_at DESC
    """, tuple(params), fetch="all")
    
    context = {
        'fds': fds,
        'status_filter': status_filter,
        'search': search,
        'status_choices': [
            ('ACTIVE', 'Active'),
            ('MATURED', 'Matured'),
            ('PREMATURE_CLOSED', 'Prematurely Closed'),
            ('PENDING', 'Pending'),
        ],
    }
    
    return render(request, 'bank_app/admin/admin_fd_list.html', context)


@admin_login_required
def admin_fd_detail(request, fd_id):
    """View fixed deposit details."""
    fd = get_record_by_id('fixed_deposit', fd_id)
    
    if not fd:
        return redirect('admin_panel:admin_fd_list')
    
    # Get user details
    user_id = fd.get('user_id')
    user = get_record_by_id('users', user_id) if user_id else None
    
    # Get related transactions
    transactions = get_all_records(
        'transactions',
        "fd_id = ?",
        (fd_id,),
        order_by='txn_date DESC'
    )
    
    context = {
        'fd': fd,
        'user': user,
        'transactions': transactions,
    }
    
    return render(request, 'bank_app/admin/admin_fd_detail.html', context)


# =============================================================================
# COMPLIANCE & AML
# =============================================================================

@admin_login_required
def admin_aml_cases(request):
    """View AML cases."""
    risk_band = request.GET.get('risk_band', 'all')
    decision = request.GET.get('decision', 'all')
    
    conditions = []
    params = []
    
    if risk_band != 'all' and risk_band:
        conditions.append("risk_band = ?")
        params.append(risk_band)
    
    if decision != 'all' and decision:
        conditions.append("decision = ?")
        params.append(decision)
    
    where_clause = ""
    if conditions:
        where_clause = " AND ".join(conditions)
    
    cases = execute_raw_sql(f"""
        SELECT a.*, u.email as user_email
        FROM aml_cases a
        LEFT JOIN users u ON a.user_id = u.user_id
        {f'WHERE {where_clause}' if where_clause else ''}
        ORDER BY a.created_at DESC
    """, tuple(params), fetch="all")
    
    context = {
        'cases': cases,
        'risk_band': risk_band,
        'decision': decision,
        'risk_bands': ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'],
        'decisions': ['APPROVED', 'REJECTED', 'REQUIRES_REVIEW'],
    }
    
    return render(request, 'bank_app/admin/admin_aml_cases.html', context)


@admin_login_required
def admin_compliance_audit_log(request):
    """View compliance audit logs."""
    event_type = request.GET.get('event_type', 'all')
    
    conditions = []
    params = []
    
    if event_type != 'all' and event_type:
        conditions.append("event_type = ?")
        params.append(event_type)
    
    where_clause = ""
    if conditions:
        where_clause = " AND ".join(conditions)
    
    logs = execute_raw_sql(f"""
        SELECT * FROM compliance_audit_log {f'WHERE {where_clause}' if where_clause else ''}
        ORDER BY logged_at DESC LIMIT 100
    """, tuple(params), fetch="all")
    
    context = {
        'logs': logs,
        'event_type': event_type,
    }
    
    return render(request, 'bank_app/admin/admin_compliance_audit.html', context)


# =============================================================================
# KYC VERIFICATION
# =============================================================================

@admin_login_required
def admin_kyc_list(request):
    """View KYC verification records."""
    status = request.GET.get('status', 'all')
    
    conditions = []
    params = []
    
    if status != 'all' and status:
        conditions.append("kyc_status = ?")
        params.append(status)
    
    where_clause = ""
    if conditions:
        where_clause = " AND ".join(conditions)
    
    kyc_records = execute_raw_sql(f"""
        SELECT k.*, u.email as user_email, u.first_name, u.last_name
        FROM kyc_verification k
        LEFT JOIN users u ON k.user_id = u.user_id
        {f'WHERE {where_clause}' if where_clause else ''}
        ORDER BY k.created_at DESC
    """, tuple(params), fetch="all")
    
    context = {
        'kyc_records': kyc_records,
        'status': status,
        'status_choices': [
            ('PENDING', 'Pending'),
            ('VERIFIED', 'Verified'),
            ('REJECTED', 'Rejected'),
            ('REQUIRES_REVIEW', 'Requires Review'),
        ],
    }
    
    return render(request, 'bank_app/admin/admin_kyc_list.html', context)


# =============================================================================
# MODEL MANAGEMENT - Main page showing all legacy tables
# =============================================================================

@admin_login_required
def admin_model_management(request):
    """Main model management page - shows all legacy database tables with counts."""
    # Get counts for all legacy tables
    table_counts = get_table_counts()
    
    # Map legacy table names to display info
    models = [
        {'name': 'loan_applications', 'label': 'Loan Applications', 'icon': '💰', 'count': table_counts.get('loan_applications', 0)},
        {'name': 'fixed_deposit', 'label': 'Fixed Deposits', 'icon': '💵', 'count': table_counts.get('fixed_deposit', 0)},
        {'name': 'users', 'label': 'Users', 'icon': '👤', 'count': table_counts.get('users', 0)},
        {'name': 'accounts', 'label': 'Accounts', 'icon': '🏦', 'count': table_counts.get('accounts', 0)},
        {'name': 'kyc_verification', 'label': 'KYC Verification', 'icon': '📄', 'count': table_counts.get('kyc_verification', 0)},
        {'name': 'aml_cases', 'label': 'AML Cases', 'icon': '🔍', 'count': table_counts.get('aml_cases', 0)},
        {'name': 'compliance_audit_log', 'label': 'Compliance Audit Logs', 'icon': '📋', 'count': table_counts.get('compliance_audit_log', 0)},
        {'name': 'transactions', 'label': 'Transactions', 'icon': '💳', 'count': table_counts.get('transactions', 0)},
        {'name': 'interest_rates_catalog', 'label': 'Interest Rates', 'icon': '📊', 'count': table_counts.get('interest_rates_catalog', 0)},
        {'name': 'loan_disbursements', 'label': 'Loan Disbursements', 'icon': '💸', 'count': table_counts.get('loan_disbursements', 0)},
        {'name': 'address', 'label': 'Addresses', 'icon': '📍', 'count': table_counts.get('address', 0)},
    ]
    
    context = {
        'models': models,
    }
    return render(request, 'bank_app/admin/admin_model_management.html', context)


# =============================================================================
# UTILITY: Database path info
# =============================================================================

def get_db_info():
    """Get information about the legacy database."""
    return {
        'path': str(LEGACY_DB_PATH),
        'exists': LEGACY_DB_PATH.exists(),
    }


# =============================================================================
# STUB VIEWS FOR COMPATIBILITY (These can be implemented later if needed)
# =============================================================================

@admin_login_required
def admin_audit_log(request):
    """View audit logs - uses compliance_audit_log from legacy DB."""
    logs = get_all_records('compliance_audit_log', order_by='logged_at DESC', limit=100)
    context = {
        'logs': logs,
        'action_filter': 'all',
        'date_from': '',
        'date_to': '',
        'search': '',
        'action_choices': [('ALL', 'All'), ('CREATE', 'Create'), ('UPDATE', 'Update'), ('DELETE', 'Delete')],
    }
    return render(request, 'bank_app/admin/admin_audit_log.html', context)


@admin_login_required
def admin_crew_logs(request):
    """View CrewAI logs - stub for compatibility (no legacy equivalent)."""
    context = {
        'logs': [],
        'crew_type': 'all',
        'decision': 'all',
        'crew_types': ['credit_risk', 'aml', 'fd_advisor', 'mortgage', 'news'],
        'decisions': ['APPROVED', 'REJECTED', 'REQUIRES_REVIEW'],
    }
    return render(request, 'bank_app/admin/admin_crew_logs.html', context)


@admin_login_required
def admin_content(request):
    """Content management - uses interest_rates_catalog."""
    fd_rates = get_all_records('interest_rates_catalog', order_by='effective_date DESC')
    context = {'fd_rates': fd_rates}
    return render(request, 'bank_app/admin/admin_content.html', context)


@admin_login_required
@require_POST
def admin_update_fd_rate(request, rate_id):
    """Update FD rate."""
    success = update_record('interest_rates_catalog', rate_id, {
        'is_active': 1 if request.POST.get('is_active') == 'on' else 0,
    })
    return JsonResponse({'success': success, 'rate_id': rate_id})


@admin_login_required
@require_POST
def admin_add_fd_rate(request):
    """Add FD rate."""
    bank_name = request.POST.get('bank_name')
    rate = float(request.POST.get('rate', 0))
    tenure_min_months = int(request.POST.get('tenure_min_months', 0))
    tenure_max_months = int(request.POST.get('tenure_max_months', 0))

    if bank_name and rate and tenure_min_months and tenure_max_months:
        create_record('interest_rates_catalog', {
            'bank_name': bank_name,
            'product_type': 'FIXED_DEPOSIT',
            'general_rate': rate,
            'tenure_min_months': tenure_min_months,
            'tenure_max_months': tenure_max_months,
            'effective_date': timezone.now().date().isoformat(),
            'is_active': 1,
        })
        return JsonResponse({'success': True})
    return JsonResponse({'error': 'Missing required fields'}, status=400)


@admin_login_required
def admin_email_campaigns(request):
    """Email campaigns - stub (no legacy equivalent)."""
    context = {'campaigns': [], 'active_count': 0, 'total_sent': 0, 'delivery_rate': '0%'}
    return render(request, 'bank_app/admin/admin_email_campaigns.html', context)


@admin_login_required
@require_POST
def admin_create_campaign(request):
    return JsonResponse({'success': False, 'error': 'Not implemented'}, status=501)


@admin_login_required
@require_POST
def admin_update_campaign(request, campaign_id):
    return JsonResponse({'success': False, 'error': 'Not implemented'}, status=501)


@admin_login_required
def admin_get_campaign(request, campaign_id):
    return JsonResponse({'success': False, 'error': 'Not implemented'}, status=501)


@admin_login_required
@require_POST
def admin_send_campaign(request, campaign_id):
    return JsonResponse({'success': False, 'error': 'Not implemented'}, status=501)


@admin_login_required
def admin_preview_template(request, campaign_id):
    return JsonResponse({'success': False, 'error': 'Not implemented'}, status=501)


@admin_login_required
def admin_get_campaign_stats(request, campaign_id):
    return JsonResponse({'success': False, 'error': 'Not implemented'}, status=501)


@admin_login_required
@require_POST
def admin_pause_campaign(request, campaign_id):
    return JsonResponse({'success': False, 'error': 'Not implemented'}, status=501)


@admin_login_required
def admin_campaign_logs(request, campaign_id):
    context = {'campaign': None, 'logs': []}
    return render(request, 'bank_app/admin/admin_email_campaign_logs.html', context)


@admin_login_required
@require_POST
def admin_generate_template(request):
    return JsonResponse({'success': False, 'error': 'Not implemented'}, status=501)


@admin_login_required
def admin_database_query(request):
    """Database query interface - stub."""
    return render(request, 'bank_app/admin/admin_database_query.html', {
        'action_choices': [('SUCCESS', 'Success'), ('FAILED', 'Failed'), ('BLOCKED', 'Blocked')]
    })


@admin_login_required
@require_POST
def admin_database_query_api(request):
    return JsonResponse({'success': False, 'error': 'Not implemented'}, status=501)


@admin_login_required
def admin_query_history(request):
    return JsonResponse({'success': False, 'error': 'Not implemented'}, status=501)


@admin_login_required
def admin_query_audit_log(request):
    return JsonResponse({'success': False, 'error': 'Not implemented'}, status=501)


# Model Management API endpoints (for CRUD operations on legacy tables)
@admin_login_required
def admin_model_list(request, model_name):
    """List records for a model - uses legacy tables."""
    table_map = {
        'loan-application': 'loan_applications',
        'fixed-deposit': 'fixed_deposit',
        'users': 'users',
        'accounts': 'accounts',
        'kyc_verification': 'kyc_verification',
        'aml_cases': 'aml_cases',
        'compliance_audit_log': 'compliance_audit_log',
        'transactions': 'transactions',
        'interest_rates_catalog': 'interest_rates_catalog',
        'loan_disbursements': 'loan_disbursements',
        'address': 'address',
    }

    if model_name not in table_map:
        return JsonResponse({'error': f'Unknown model: {model_name}'}, status=404)

    table = table_map[model_name]
    search = request.GET.get('search', '')
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 50))

    # Build table-specific search conditions
    conditions = []
    params = []
    
    if search:
        search_param = f"%{search}%"
        # Define searchable columns per table
        if table == 'loan_applications':
            conditions.append("(application_id LIKE ? OR applicant_email LIKE ? OR user_id LIKE ?)")
            params.extend([search_param, search_param, search_param])
        elif table == 'fixed_deposit':
            conditions.append("(fd_id LIKE ? OR user_id LIKE ? OR bank_name LIKE ? OR customer_email LIKE ?)")
            params.extend([search_param, search_param, search_param, search_param])
        elif table == 'users':
            conditions.append("(user_id LIKE ? OR email LIKE ? OR first_name LIKE ? OR last_name LIKE ?)")
            params.extend([search_param, search_param, search_param, search_param])
        elif table == 'accounts':
            conditions.append("(account_id LIKE ? OR user_id LIKE ? OR account_number LIKE ?)")
            params.extend([search_param, search_param, search_param])
        elif table == 'kyc_verification':
            conditions.append("(kyc_id LIKE ? OR user_id LIKE ? OR kyc_details_1 LIKE ?)")
            params.extend([search_param, search_param, search_param])
        elif table == 'aml_cases':
            conditions.append("(case_id LIKE ? OR user_id LIKE ? OR risk_band LIKE ?)")
            params.extend([search_param, search_param, search_param])
        elif table == 'compliance_audit_log':
            conditions.append("(log_id LIKE ? OR user_id LIKE ? OR event_type LIKE ?)")
            params.extend([search_param, search_param, search_param])
        elif table == 'transactions':
            conditions.append("(txn_id LIKE ? OR user_id LIKE ? OR fd_id LIKE ? OR txn_type LIKE ?)")
            params.extend([search_param, search_param, search_param, search_param])
        elif table == 'interest_rates_catalog':
            conditions.append("(rate_id LIKE ? OR bank_name LIKE ? OR product_type LIKE ?)")
            params.extend([search_param, search_param, search_param])
        elif table == 'loan_disbursements':
            conditions.append("(disbursement_id LIKE ? OR application_id LIKE ? OR user_id LIKE ?)")
            params.extend([search_param, search_param, search_param])
        elif table == 'address':
            conditions.append("(address_id LIKE ? OR user_id LIKE ? OR country_code LIKE ?)")
            params.extend([search_param, search_param, search_param])

    where_clause = " AND ".join(conditions) if conditions else ""
    offset = (page - 1) * per_page
    
    # Use get_all_records with proper parameters
    records = get_all_records(
        table,
        where_clause=where_clause,
        params=tuple(params),
        order_by='rowid DESC',
        limit=per_page,
        offset=offset
    )

    # Get total count
    total = count_records(table, where_clause, tuple(params))

    # Extract field names from the first record for table headers
    fields = []
    if records and len(records) > 0:
        fields = list(records[0].keys())

    # Define table-specific searchable fields
    field_mapping = {
        'loan_applications': ['application_id', 'user_id', 'applicant_email', 'loan_amnt', 'loan_decision', 'created_at'],
        'fixed_deposit': ['fd_id', 'user_id', 'bank_name', 'fd_status', 'initial_amount', 'created_at'],
        'users': ['user_id', 'first_name', 'last_name', 'account_number', 'email', 'created_at'],
        'accounts': ['account_id', 'user_id', 'account_number', 'account_type', 'balance', 'created_at'],
        'kyc_verification': ['kyc_id', 'user_id', 'kyc_status', 'kyc_details_1', 'created_at'],
        'aml_cases': ['case_id', 'user_id', 'risk_band', 'decision', 'risk_score', 'created_at'],
        'compliance_audit_log': ['log_id', 'user_id', 'event_type', 'performed_by', 'logged_at'],
        'transactions': ['txn_id', 'user_id', 'fd_id', 'txn_type', 'txn_amount', 'txn_date'],
        'interest_rates_catalog': ['rate_id', 'bank_name', 'product_type', 'general_rate', 'effective_date'],
        'loan_disbursements': ['disbursement_id', 'application_id', 'user_id', 'sanctioned_amount', 'created_at'],
        'address': ['address_id', 'user_id', 'country_code', 'mobile_number', 'created_at'],
    }
    filter_fields = field_mapping.get(table, ['id', 'created_at'])

    return JsonResponse({
        'success': True,
        'model': model_name,
        'label': model_name.replace('-', ' ').title(),
        'records': records,
        'fields': fields,
        'filter_fields': filter_fields,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page if per_page > 0 else 0
        }
    })


@admin_login_required
def admin_model_detail(request, model_name, record_id):
    """Get record detail - uses legacy tables."""
    table_map = {
        'loan-application': 'loan_applications',
        'fixed-deposit': 'fixed_deposit',
        'users': 'users',
        'accounts': 'accounts',
        'kyc_verification': 'kyc_verification',
        'aml_cases': 'aml_cases',
        'compliance_audit_log': 'compliance_audit_log',
        'transactions': 'transactions',
        'interest_rates_catalog': 'interest_rates_catalog',
        'loan_disbursements': 'loan_disbursements',
        'address': 'address',
    }

    if model_name not in table_map:
        return JsonResponse({'error': f'Unknown model: {model_name}'}, status=404)

    table = table_map[model_name]
    
    try:
        record = get_record_by_id(table, int(record_id))
        
        if not record:
            return JsonResponse({'error': 'Record not found'}, status=404)
        
        return JsonResponse({'success': True, 'record': record})
    except Exception as e:
        return JsonResponse({'error': f'Invalid record ID: {str(e)}'}, status=400)


@admin_login_required
@require_POST
def admin_model_create(request, model_name):
    """Create record - uses legacy tables."""
    table_map = {
        'loan-application': 'loan_applications',
        'fixed-deposit': 'fixed_deposit',
        'users': 'users',
        'accounts': 'accounts',
        'kyc_verification': 'kyc_verification',
        'aml_cases': 'aml_cases',
        'compliance_audit_log': 'compliance_audit_log',
        'transactions': 'transactions',
        'interest_rates_catalog': 'interest_rates_catalog',
        'loan_disbursements': 'loan_disbursements',
        'address': 'address',
    }
    
    if model_name not in table_map:
        return JsonResponse({'error': f'Unknown model: {model_name}'}, status=404)
    
    table = table_map[model_name]
    try:
        data = json.loads(request.body)
        # Remove read-only ID fields
        for field in ['application_id', 'fd_id', 'user_id', 'txn_id', 'case_id', 'log_id', 'rate_id', 'disbursement_id', 'address_id', 'kyc_id']:
            data.pop(field, None)
        
        result = create_record(table, data)
        if result:
            pk = result.get('application_id') or result.get('fd_id') or result.get('user_id') or result.get('id')
            return JsonResponse({'success': True, 'id': pk, 'message': 'Record created successfully'})
        return JsonResponse({'success': False, 'error': 'Failed to create record'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@admin_login_required
@require_POST
def admin_model_update(request, model_name, record_id):
    """Update record - uses legacy tables."""
    table_map = {
        'loan-application': 'loan_applications',
        'fixed-deposit': 'fixed_deposit',
        'users': 'users',
        'accounts': 'accounts',
        'kyc_verification': 'kyc_verification',
        'aml_cases': 'aml_cases',
        'compliance_audit_log': 'compliance_audit_log',
        'transactions': 'transactions',
        'interest_rates_catalog': 'interest_rates_catalog',
        'loan_disbursements': 'loan_disbursements',
        'address': 'address',
    }
    
    if model_name not in table_map:
        return JsonResponse({'error': f'Unknown model: {model_name}'}, status=404)
    
    table = table_map[model_name]
    try:
        data = json.loads(request.body)
        # Remove read-only ID fields
        for field in ['application_id', 'fd_id', 'user_id', 'txn_id', 'case_id', 'log_id', 'rate_id', 'disbursement_id', 'address_id', 'kyc_id']:
            data.pop(field, None)
        
        success = update_record(table, record_id, data)
        return JsonResponse({'success': success, 'message': 'Record updated successfully' if success else 'Update failed'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@admin_login_required
@require_POST
def admin_model_delete(request, model_name, record_id):
    """Delete record - uses legacy tables."""
    table_map = {
        'loan-application': 'loan_applications',
        'fixed-deposit': 'fixed_deposit',
        'users': 'users',
        'accounts': 'accounts',
        'kyc_verification': 'kyc_verification',
        'aml_cases': 'aml_cases',
        'compliance_audit_log': 'compliance_audit_log',
        'transactions': 'transactions',
        'interest_rates_catalog': 'interest_rates_catalog',
        'loan_disbursements': 'loan_disbursements',
        'address': 'address',
    }
    
    if model_name not in table_map:
        return JsonResponse({'error': f'Unknown model: {model_name}'}, status=404)
    
    table = table_map[model_name]
    try:
        success = delete_record(table, record_id)
        return JsonResponse({'success': success, 'message': 'Record deleted successfully' if success else 'Delete failed'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
