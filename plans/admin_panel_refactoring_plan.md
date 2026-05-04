# Admin Panel Refactoring Plan (Updated)

## Executive Summary

Based on the actual database schema examination, this document outlines the complete overhaul of the custom admin panel (`Test/bank_app/admin_views.py` and `Test/bank_app/templates/bank_app/admin/`).

**Key Finding**: The database contains **35 tables** - 11 legacy tables from `create_db.py` PLUS Django ORM tables. The templates expect fields from **Django ORM tables** (`bank_app_loanapplication`, `bank_app_fixeddeposit`, `bank_app_usersession`) but the admin views query **legacy tables** (`loan_applications`, `fixed_deposit`, `users`).

### Critical Discovery

| Template Expects | Legacy Table Has | Django ORM Table Has |
|------------------|------------------|---------------------|
| `applicant_name` | ❌ (only `applicant_email`) | ✅ `bank_app_loanapplication.applicant_name` |
| `loan_amount` | ❌ (`loan_amnt`) | ✅ `bank_app_loanapplication.loan_amount` |
| `status` | ❌ (`loan_decision`) | ✅ `bank_app_loanapplication.status` |
| `region` | ❌ (in `address.country_code`) | ✅ `bank_app_loanapplication.region` |
| `get_status_display()` | ❌ (raw dict) | ✅ (Django model method) |

**Decision Point**: Should the admin panel use:
- **Option A**: Legacy tables (`loan_applications`, `fixed_deposit`) - requires template changes
- **Option B**: Django ORM tables (`bank_app_loanapplication`, `bank_app_fixeddeposit`) - requires view changes

Given the templates are already designed for Django ORM fields, **Option B is recommended**.

---

## Database Schema Summary

### Legacy Tables (from `create_db.py`) - 11 tables
| Table | Purpose | Used by Admin? |
|-------|---------|----------------|
| `users` | Core user identity | ✅ Yes (dashboard) |
| `address` | Contact/location | ✅ Yes (regional data) |
| `kyc_verification` | KYC documents | ✅ Yes (KYC list) |
| `accounts` | Bank accounts | ⚠️ Referenced |
| `fixed_deposit` | FD/RD products | ✅ Yes (FD list) |
| `transactions` | Transaction audit | ✅ Yes |
| `aml_cases` | AML screening | ✅ Yes |
| `compliance_audit_log` | Compliance events | ✅ Yes |
| `interest_rates_catalog` | FD rates | ✅ Yes (config) |
| `loan_applications` | Loan applications | ✅ Yes (but wrong fields) |
| `loan_disbursements` | Loan disbursements | ✅ Yes |

### Django ORM Tables - 24 tables (relevant ones)
| Table | Purpose | Admin Uses? |
|-------|---------|-------------|
| `bank_app_usersession` | User session tracking | ✅ Yes (user list) |
| `bank_app_loanapplication` | Loan applications with full fields | ⚠️ Templates expect this |
| `bank_app_fixeddeposit` | FD records with Django fields | ⚠️ Templates expect this |
| `bank_app_auditlog` | Audit logs | ✅ Yes (activity log) |
| `auth_user` | Django authentication | ✅ For admin login |

---

## Implementation Strategy

### Phase 1: Security Hardening

#### 1.1 Replace Hardcoded Password with Django Authentication

**File**: [`admin_views.py`](Test/bank_app/admin_views.py:52-63)

**Current (INSECURE)**:
```python
def admin_login(request):
    if request.method == 'POST':
        password = request.POST.get('password')
        if password == 'admin123':  # HARDCODED!
            request.session['admin_logged_in'] = True
```

**New (SECURE)**:
```python
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required

def admin_login(request):
    """Secure admin login using Django authentication."""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None and user.is_staff:
            login(request, user)
            request.session.set_expiry(3600)  # 1 hour
            return redirect('admin_panel:admin_dashboard')
        return render(request, 'bank_app/admin/admin_login.html', {
            'error': 'Invalid credentials or insufficient permissions'
        })
    return render(request, 'bank_app/admin/admin_login.html')

def admin_logout(request):
    logout(request)
    return redirect('admin_panel:admin_login')
```

**Template Changes** ([`admin_login.html`](Test/bank_app/templates/bank_app/admin/admin_login.html)):
```django
<form method="post">
    {% csrf_token %}
    <input type="text" name="username" placeholder="Username" required>
    <input type="password" name="password" placeholder="Password" required>
    <button type="submit">Login</button>
</form>
```

**Setup Command** (run once):
```bash
python Test/manage.py createsuperuser
# Follow prompts to create admin user
```

---

### Phase 2: Align Views with Correct Tables

#### 2.1 Loan Applications - Use Django ORM Table

**Current Issue**: [`admin_views.py`](Test/bank_app/admin_views.py:253-256) queries `loan_applications` (legacy) but templates expect `bank_app_loanapplication` fields.

**Option A: Switch to Django ORM** (Recommended)

```python
from bank_app.models import LoanApplication  # Django ORM model

@admin_login_required
def admin_transaction_list(request):
    type_filter = request.GET.get('type', 'all')
    status_filter = request.GET.get('status', 'all')
    search = request.GET.get('search', '')
    
    loans = []
    fds = []
    
    if type_filter in ['loan', 'all']:
        # Use Django ORM model
        loan_qs = LoanApplication.objects.all()
        
        if status_filter != 'all' and status_filter:
            loan_qs = loan_qs.filter(status=status_filter)
        
        if search:
            loan_qs = loan_qs.filter(
                applicant_name__icontains=search | 
                applicant_email__icontains=search
            )
        
        loans = list(loan_qs.order_by('-created_at')[:50])
        # Convert to dict for template consistency
        loans = [
            {
                'application_id': l.application_id,
                'applicant_name': l.applicant_name,
                'loan_amount': l.loan_amount,
                'status': l.status,
                'loan_decision': l.status,  # For template compatibility
                'created_at': l.created_at,
            }
            for l in loans
        ]
    
    # ... similar for FDs
```

**Option B: Keep Legacy Tables, Fix Templates**

If you prefer to keep using legacy tables, update templates:
- `loan.applicant_name` → `loan.applicant_email`
- `loan.loan_amount` → `loan.loan_amnt`
- `loan.status` → `loan.loan_decision`
- Remove `.get_status_display()` calls

---

### Phase 3: Fix Template Issues

#### 3.1 Remove `.get_*_display()` Calls

**Problem**: Raw SQL dictionaries don't have Django model methods.

**Template Fix** ([`admin_analytics.html`](Test/bank_app/templates/bank_app/admin/admin_analytics.html:56)):
```django
<!-- BEFORE (breaks with raw SQL) -->
{{ region.get_region_display }}

<!-- AFTER (works with both) -->
{{ region.region }}  <!-- or region.country_code -->
```

#### 3.2 Fix Regional Data Display

**File**: [`admin_views.py`](Test/bank_app/admin_views.py:406-414)

```python
# Add country name mapping
from utils.geolocation import get_all_countries

regional_loans = execute_raw_sql("""
    SELECT a.country_code, COUNT(*) as count
    FROM loan_applications la
    LEFT JOIN users u ON la.user_id = u.user_id
    LEFT JOIN address a ON u.user_id = a.user_id
    GROUP BY a.country_code
    ORDER BY count DESC
""", fetch="all")

# Convert to template-friendly format
all_countries = get_all_countries()
regional_loans_formatted = []
for region in regional_loans:
    country_code = region.get('country_code', '')
    country_name = all_countries.get(country_code, {}).get('name', country_code)
    regional_loans_formatted.append({
        'country_code': country_code,
        'region': country_name,  # Template expects 'region'
        'count': region['count']
    })

context['regional_loans'] = regional_loans_formatted
```

---

## File Change Summary

| File | Changes | Priority |
|------|---------|----------|
| `admin_views.py` | Replace hardcoded auth with Django auth; Fix table references | Critical |
| `admin_login.html` | Add username field, CSRF token | Critical |
| `admin_dashboard.html` | Fix activity log field references | High |
| `admin_transactions.html` | Fix field names OR switch to ORM models | High |
| `admin_analytics.html` | Remove `.get_*_display()` calls | High |
| `admin_user_list.html` | Verify uses `bank_app_usersession` | Medium |

---

## Decision Required

Before implementation, please confirm:

1. **Table Strategy**: Use Django ORM tables (`bank_app_loanapplication`) OR legacy tables (`loan_applications`)?
   - Django ORM: Templates work as-is, but views need rewriting
   - Legacy tables: Views mostly work, but templates need fixing

2. **Authentication**: Use Django's `auth_user` for admin login? (requires `createsuperuser`)

3. **Session Timeout**: 1 hour (3600 seconds) OK?

---

## Recommended Approach

**Use Django ORM tables** because:
1. Templates already expect those field names
2. Django models provide `.get_*_display()` methods
3. Better integration with existing Django features
4. Easier to maintain long-term

**Implementation Order**:
1. Create admin user via `createsuperuser`
2. Update `admin_views.py` to use Django ORM models
3. Fix any remaining template issues
4. Test all admin pages
5. Remove unused imports

---

## Testing Checklist

- [ ] Admin login with Django credentials works
- [ ] Dashboard shows correct counts
- [ ] Transaction list displays loan applications correctly
- [ ] Analytics page shows regional breakdown
- [ ] All CRUD operations work
- [ ] No console errors
- [ ] CSRF protection active
- [ ] Session timeout works
