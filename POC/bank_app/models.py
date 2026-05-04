from django.db import models
from django.utils import timezone
from decimal import Decimal
import json
import threading
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


# =============================================================================
# LOAN APPLICATION MODELS
# =============================================================================

class LoanApplication(models.Model):
    """Model for storing loan applications and their assessment results."""
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted'),
        ('UNDER_REVIEW', 'Under Review'),
        ('KYC_PENDING', 'KYC Pending'),
        ('COMPLIANCE_CHECK', 'Compliance Check'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('DISBURSED', 'Disbursed'),
    ]
    
    REGION_CHOICES = [
        ('IN', 'India'),
        ('US', 'United States'),
    ]
    
    # Application metadata
    application_id = models.CharField(max_length=50, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    region = models.CharField(max_length=2, choices=REGION_CHOICES, default='IN')
    
    # Applicant information
    applicant_name = models.CharField(max_length=200)
    applicant_email = models.EmailField(blank=True, null=True)
    applicant_phone = models.CharField(max_length=20, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    pan_number = models.CharField(max_length=20, blank=True, null=True)  # For India
    ssn_last_4 = models.CharField(max_length=4, blank=True, null=True)  # For US
    
    # Financial information
    applicant_income = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    coapplicant_income = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    employment_status = models.CharField(max_length=50, blank=True, null=True)
    employment_years = models.IntegerField(default=0)
    
    # Loan request details
    loan_amount = models.DecimalField(max_digits=15, decimal_places=2)
    loan_term_months = models.IntegerField(default=0)
    loan_purpose = models.CharField(max_length=100, blank=True, null=True)
    
    # Credit information
    credit_score = models.IntegerField(blank=True, null=True)
    dti_ratio = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    existing_loans = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Collateral information
    collateral_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    collateral_type = models.CharField(max_length=100, blank=True, null=True)
    
    # Risk assessment results (stored as JSON)
    risk_assessment = models.JSONField(blank=True, null=True)
    approval_probability = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    risk_grade = models.CharField(max_length=10, blank=True, null=True)
    
    # KYC and compliance
    kyc_status = models.CharField(max_length=20, default='PENDING')
    kyc_data = models.JSONField(blank=True, null=True)
    compliance_status = models.CharField(max_length=20, default='PENDING')
    compliance_results = models.JSONField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    decided_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['application_id']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['region', 'status']),
        ]
    
    def __str__(self):
        return f"Loan Application {self.application_id} - {self.applicant_name}"
    
    def save(self, *args, **kwargs):
        # Generate application ID if new
        if not self.application_id:
            timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
            self.application_id = f"APP{timestamp}"
    
        # Set submitted_at when status changes to SUBMITTED
        if self.status == 'SUBMITTED' and not self.submitted_at:
            self.submitted_at = timezone.now()
    
        # Set decided_at when status is APPROVED or REJECTED
        if self.status in ('APPROVED', 'REJECTED') and not self.decided_at:
            self.decided_at = timezone.now()
    
        # Store old instance for comparison (before save)
        old_instance = None
        if self.pk:
            try:
                old_instance = LoanApplication.objects.get(pk=self.pk)
            except LoanApplication.DoesNotExist:
                pass
    
        # Call parent save
        super().save(*args, **kwargs)
    
        # AUDIT LOGGING: Track status and compliance changes after save
        if old_instance:
            timestamp = timezone.now()
            
            # Check status change
            if old_instance.status != self.status:
                action = self._get_action_from_status(self.status)
                AuditLog.objects.create(
                    application=self,
                    action=action,
                    actor_type=self._get_actor_type(),
                    actor_id=self._get_actor_id(),
                    details={
                        'old_status': old_instance.status,
                        'new_status': self.status,
                        'timestamp': timestamp.isoformat(),
                        'ip_address': self._get_ip_address()
                    },
                    ip_address=self._get_ip_address()
                )
                self._broadcast_status_update(old_instance.status, self.status)
            
            # Check KYC status change
            if old_instance.kyc_status != self.kyc_status:
                AuditLog.objects.create(
                    application=self,
                    action='KYC_UPDATED',
                    actor_type=self._get_actor_type(),
                    actor_id=self._get_actor_id(),
                    details={
                        'old_kyc_status': old_instance.kyc_status,
                        'new_kyc_status': self.kyc_status,
                        'timestamp': timestamp.isoformat()
                    }
                )
            
            # Check compliance status change
            if old_instance.compliance_status != self.compliance_status:
                AuditLog.objects.create(
                    application=self,
                    action='COMPLIANCE_UPDATED',
                    actor_type=self._get_actor_type(),
                    actor_id=self._get_actor_id(),
                    details={
                        'old_compliance_status': old_instance.compliance_status,
                        'new_compliance_status': self.compliance_status,
                        'timestamp': timestamp.isoformat()
                    }
                )
    
    def _get_action_from_status(self, status):
        """Map status to audit action."""
        status_to_action = {
            'SUBMITTED': 'LOAN_SUBMITTED',
            'APPROVED': 'LOAN_APPROVED',
            'REJECTED': 'LOAN_REJECTED',
            'UNDER_REVIEW': 'LOAN_UPDATED',
            'KYC_PENDING': 'LOAN_UPDATED',
            'COMPLIANCE_CHECK': 'COMPLIANCE_CHECKED',
            'DISBURSED': 'LOAN_UPDATED',
        }
        return status_to_action.get(status, 'LOAN_UPDATED')
    
    def _get_actor_type(self):
        """Get actor type from thread-local storage or default."""
        from .middleware import get_current_user_type
        return get_current_user_type() or 'SYSTEM'
    
    def _get_actor_id(self):
        """Get actor ID from thread-local storage or default."""
        from .middleware import get_current_user_id
        return get_current_user_id() or 'anonymous'
    
    def _get_ip_address(self):
        """Get IP address from thread-local storage or default."""
        from .middleware import get_current_ip_address
        return get_current_ip_address()
    
    def _broadcast_status_update(self, old_status, new_status):
        """Broadcast status update via WebSocket."""
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                'dashboard_updates',
                {
                    'type': 'loan_status_update',
                    'loan_id': self.id,
                    'application_id': self.application_id,
                    'old_status': old_status,
                    'new_status': new_status,
                    'timestamp': timezone.now().isoformat()
                }
            )
        except Exception as e:
            # Silently fail if channels not configured
            pass


# =============================================================================
# FIXED DEPOSIT MODELS
# =============================================================================

class BankFDRate(models.Model):
    """Model for storing fixed deposit rates from various banks."""
    
    bank_name = models.CharField(max_length=200)
    rate = models.DecimalField(max_digits=5, decimal_places=2)  # Interest rate %
    min_deposit = models.DecimalField(max_digits=15, decimal_places=2)
    max_deposit = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    tenure_months = models.IntegerField()
    tenure_type = models.CharField(max_length=20, default='FIXED')  # FIXED, FLEXIBLE
    
    # Additional features
    senior_citizen_rate = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    premature_withdrawal = models.BooleanField(default=True)
    loan_against_fd = models.BooleanField(default=True)
    
    # Metadata
    effective_from = models.DateField()
    effective_until = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    source = models.CharField(max_length=200, blank=True, null=True)
    
    class Meta:
        ordering = ['-rate', 'bank_name']
        indexes = [
            models.Index(fields=['is_active', 'tenure_months']),
            models.Index(fields=['bank_name', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.bank_name} - {self.rate}% for {self.tenure_months} months"


class FDComparison(models.Model):
    """Model for storing user FD comparison preferences and results."""
    
    user_session_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Comparison criteria
    deposit_amount = models.DecimalField(max_digits=15, decimal_places=2)
    tenure_preference_months = models.IntegerField()
    min_rate_required = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    
    # Results (stored as JSON for flexibility)
    comparison_results = models.JSONField(blank=True, null=True)
    selected_bank = models.CharField(max_length=200, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"FD Comparison for {self.deposit_amount} - {self.created_at}"


# =============================================================================
# FD/TD CREATION MODEL
# =============================================================================

class FixedDeposit(models.Model):
    """Model for storing created Fixed/Term Deposits - uses custom fixed_deposit table."""

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('ACTIVE', 'Active'),
        ('MATURED', 'Matured'),
        ('CLOSED', 'Closed'),
        ('PREMATURELY_CLOSED', 'Prematurely Closed'),
    ]

    REGION_CHOICES = [
        ('IN', 'India'),
        ('US', 'United States'),
    ]

    # FD identification - matches custom schema (fd_id is the INTEGER PRIMARY KEY)
    fd_id = models.AutoField(primary_key=True, db_column='fd_id')
    account_number = models.CharField(max_length=50, blank=True, null=True, db_column='account_number')
    # Map status to fd_status in custom schema - default to 'ACTIVE' to match custom schema
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', db_column='fd_status')
    region = models.CharField(max_length=2, choices=REGION_CHOICES, default='IN', db_column='region')

    # Foreign key to users table (custom schema requires this, but we make it optional for Django usage)
    user_id = models.IntegerField(blank=True, null=True, db_column='user_id')
  
    # Customer information
    user_session_id = models.CharField(max_length=100, blank=True, null=True, db_column='user_session_id')
    customer_name = models.CharField(max_length=200, blank=True, null=True, db_column='customer_name')
    customer_email = models.EmailField(blank=True, null=True, db_column='customer_email')
    customer_phone = models.CharField(max_length=20, blank=True, null=True, db_column='customer_phone')

    # FD details - map to custom schema column names
    bank_name = models.CharField(max_length=200, db_column='bank_name')
    # Map rate to interest_rate in custom schema
    rate = models.DecimalField(max_digits=5, decimal_places=2, db_column='interest_rate')
    # Map amount to initial_amount in custom schema
    amount = models.DecimalField(max_digits=15, decimal_places=2, db_column='initial_amount')
    tenure_months = models.IntegerField(db_column='tenure_months')

    # Dates - start_date required for FD creation
    start_date = models.DateField(db_column='start_date')
    maturity_date = models.DateField(blank=True, null=True, db_column='maturity_date')

    # Calculated amounts
    maturity_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, db_column='maturity_amount')
    interest_earned = models.DecimalField(max_digits=15, decimal_places=2, default=0, db_column='interest_earned')

    # Features - map to INTEGER columns in SQLite
    senior_citizen = models.BooleanField(default=False, db_column='senior_citizen')
    loan_against_fd = models.BooleanField(default=False, db_column='loan_against_fd')
    auto_renewal = models.BooleanField(default=False, db_column='auto_renewal')

    # Certificate and documents
    certificate_path = models.CharField(max_length=500, blank=True, null=True, db_column='certificate_path')
    certificate_generated = models.BooleanField(default=False, db_column='certificate_generated')

    # Email notification
    email_sent = models.BooleanField(default=False, db_column='email_sent')
    email_sent_at = models.DateTimeField(blank=True, null=True, db_column='email_sent_at')

    # Additional custom schema columns
    product_type = models.CharField(max_length=10, default='FD', db_column='product_type')
    monthly_installment = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, db_column='monthly_installment')
    compounding_freq = models.CharField(max_length=20, default='quarterly', db_column='compounding_freq')
    premature_penalty_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, db_column='premature_penalty_percent')
    confirmed_at = models.DateTimeField(blank=True, null=True, db_column='confirmed_at')
    risk_score = models.IntegerField(blank=True, null=True, db_column='risk_score')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')

    class Meta:
        db_table = 'fixed_deposit'  # Use custom table name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['fd_id']),
            models.Index(fields=['customer_email']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"FD {self.pk} - {self.bank_name} - ₹{self.amount}"
  
    def save(self, *args, **kwargs):
        # Calculate maturity amount and interest if not set
        if self.amount and self.rate and self.tenure_months:
            # Compound interest formula: A = P(1 + r/n)^(nt)
            # For monthly compounding: A = P(1 + r/12)^(12*t/12) = P(1 + r/12)^t
            rate_decimal = float(self.rate) / 100
            principal = float(self.amount)
            tenure = int(self.tenure_months)
  
            maturity = principal * pow(1 + rate_decimal / 12, tenure)
            interest = maturity - principal
  
            if not self.maturity_amount:
                self.maturity_amount = round(maturity, 2)
            if not self.interest_earned:
                self.interest_earned = round(interest, 2)
  
        # Set maturity date if not set
        if self.start_date and self.tenure_months and not self.maturity_date:
            from datetime import timedelta
            months = int(self.tenure_months)
            year_add = months // 12
            month_add = months % 12
  
            start = self.start_date
            new_year = start.year + year_add
            new_month = start.month + month_add
  
            if new_month > 12:
                new_year += 1
                new_month -= 12
  
            # Handle day overflow (e.g., Jan 31 + 1 month = Feb 28/29)
            try:
                self.maturity_date = start.replace(year=new_year, month=new_month)
            except ValueError:
                # If day doesn't exist in target month, use last day of month
                import calendar
                last_day = calendar.monthrange(new_year, new_month)[1]
                self.maturity_date = start.replace(year=new_year, month=new_month, day=last_day)
  
        super().save(*args, **kwargs)
  
    @property
    def fd_id_display(self):
        """Return a human-readable FD ID string based on the primary key."""
        return f"FD{self.pk}" if self.pk else "FD (unsaved)"


# =============================================================================
# USER SESSION MODELS
# =============================================================================

class UserSession(models.Model):
    """Model for tracking user sessions."""

    session_id = models.CharField(max_length=100, unique=True)
    user_ip = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)

    # Session data (stored as JSON)
    session_data = models.JSONField(default=dict)

    # Geolocation fields
    country_code = models.CharField(max_length=2, blank=True, null=True)
    country_name = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)

    # Status
    is_active = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-last_activity']
        indexes = [
            models.Index(fields=['session_id', 'is_active']),
        ]
    
    def __str__(self):
        return f"Session {self.session_id[:20]}... - {'Active' if self.is_active else 'Inactive'}"


# =============================================================================
# KYC DOCUMENT MODELS
# =============================================================================

class KYCDocument(models.Model):
    """Model for storing KYC document information."""
    
    DOCUMENT_TYPE_CHOICES = [
        ('AADHAAR', 'Aadhaar Card'),
        ('PAN', 'PAN Card'),
        ('PASSPORT', 'Passport'),
        ('VOTER_ID', 'Voter ID'),
        ('DRIVING_LICENSE', 'Driving License'),
        ('OTHER', 'Other'),
    ]
    
    application = models.ForeignKey(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name='kyc_documents',
        blank=True,
        null=True
    )
    
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES)
    document_number = models.CharField(max_length=100)
    file_path = models.CharField(max_length=500)
    file_size = models.IntegerField(default=0)  # in bytes
    
    # Extracted data (from vision model)
    extracted_data = models.JSONField(blank=True, null=True)
    extraction_confidence = models.CharField(max_length=10, blank=True, null=True)
    
    # Verification status
    verification_status = models.CharField(max_length=20, default='PENDING')
    verified_at = models.DateTimeField(blank=True, null=True)
    
    # Timestamps
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.document_type} - {self.document_number}"


# =============================================================================
# COMPLIANCE SCREENING MODELS
# =============================================================================

class ComplianceScreening(models.Model):
    """Model for storing compliance screening results."""
    
    application = models.ForeignKey(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name='compliance_screenings',
        blank=True,
        null=True
    )
    
    entity_name = models.CharField(max_length=200)
    entity_type = models.CharField(max_length=50, default='PERSON')  # PERSON, LEGAL_ENTITY
    
    # Search parameters
    search_query = models.JSONField()
    
    # Results
    yente_results = models.JSONField(blank=True, null=True)
    wikidata_results = models.JSONField(blank=True, null=True)
    
    # Risk assessment
    is_sanctioned = models.BooleanField(default=False)
    is_pep = models.BooleanField(default=False)
    risk_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    risk_level = models.CharField(max_length=20, blank=True, null=True)
    
    # Flags
    sanctions_flags = models.JSONField(default=list, blank=True)
    pep_flags = models.JSONField(default=list, blank=True)
    
    # Status
    screening_status = models.CharField(max_length=20, default='COMPLETED')
    
    # Timestamps
    screened_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-screened_at']
    
    def __str__(self):
        return f"Compliance Screening - {self.entity_name} - {'FLAGGED' if self.is_sanctioned else 'CLEAR'}"


# =============================================================================
# EMI CALCULATION HISTORY
# =============================================================================

class EMICalculation(models.Model):
    """Model for storing EMI calculation history."""
    
    user_session_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Input parameters
    loan_amount = models.DecimalField(max_digits=15, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    tenure_months = models.IntegerField()
    calculation_method = models.CharField(max_length=50, default='Reducing Balance')
    processing_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Results (stored as JSON for full amortization schedule)
    calculation_results = models.JSONField()
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"EMI Calc - {self.loan_amount} at {self.interest_rate}% for {self.tenure_months} months"


# =============================================================================
# AUDIT LOG MODEL
# =============================================================================

class AuditLog(models.Model):
    """Model for auditing important actions."""

    ACTION_CHOICES = [
        ('LOAN_SUBMITTED', 'Loan Submitted'),
        ('LOAN_APPROVED', 'Loan Approved'),
        ('LOAN_REJECTED', 'Loan Rejected'),
        ('KYC_UPLOADED', 'KYC Uploaded'),
        ('KYC_VERIFIED', 'KYC Verified'),
        ('COMPLIANCE_CHECKED', 'Compliance Checked'),
        ('EMI_CALCULATED', 'EMI Calculated'),
        ('FD_COMPARED', 'FD Compared'),
        ('CREWAI_AUTO_APPROVED', 'CrewAI Auto Approved'),
        ('CREWAI_AUTO_REJECTED', 'CrewAI Auto Rejected'),
        ('CREWAI_REQUIRES_REVIEW', 'CrewAI Requires Human Review'),
        ('KYC_UPDATED', 'KYC Status Updated'),
        ('COMPLIANCE_UPDATED', 'Compliance Status Updated'),
        ('LOAN_UPDATED', 'Loan Updated'),
    ]
    
    application = models.ForeignKey(
        LoanApplication,
        on_delete=models.SET_NULL,
        related_name='audit_logs',
        blank=True,
        null=True
    )
    
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    actor_type = models.CharField(max_length=50, default='SYSTEM')  # SYSTEM, USER, ADMIN
    actor_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Details
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['application', 'created_at']),
            models.Index(fields=['action', 'created_at']),
        ]
    
    def __str__(self):
        return f"Audit: {self.action} - {self.created_at}"


# =============================================================================
# CREWAI REASONING LOG MODEL
# =============================================================================

class CrewAIReasoningLog(models.Model):
    """Detailed log of CrewAI decision reasoning."""

    application = models.ForeignKey(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name='crewai_reasoning_logs'
    )

    crew_type = models.CharField(max_length=50)  # credit_risk, aml, fd_advisor
    decision = models.CharField(max_length=20)  # APPROVED, REJECTED, REQUIRES_REVIEW
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2)

    # Detailed reasoning
    reasoning = models.JSONField()  # Full CrewAI output
    factors = models.JSONField(default=list)  # Key decision factors
    recommendations = models.JSONField(default=list)

    # Metadata
    executed_at = models.DateTimeField(auto_now_add=True)
    auto_executed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-executed_at']

    def __str__(self):
        return f"CrewAI {self.decision} - {self.application.application_id}"


# =============================================================================
# EMAIL CAMPAIGN MODELS
# =============================================================================

class EmailCampaign(models.Model):
    """Model for managing bulk email campaigns."""

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SCHEDULED', 'Scheduled'),
        ('SENDING', 'Sending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('PAUSED', 'Paused'),
    ]

    TEMPLATE_CHOICES = [
        ('FD_CONFIRMATION', 'FD Confirmation'),
        ('FD_MATURITY_REMINDER', 'FD Maturity Reminder'),
        ('FD_RENEWAL_OFFER', 'FD Renewal Offer'),
        ('CUSTOM', 'Custom Template'),
    ]

    # Campaign metadata
    name = models.CharField(max_length=200)
    subject = models.CharField(max_length=300)
    template_type = models.CharField(max_length=50, choices=TEMPLATE_CHOICES)
    template_content = models.TextField(blank=True, null=True)  # Generated HTML content

    # Target audience filters (stored as JSON)
    target_filters = models.JSONField(default=dict, blank=True)
    # Example: {"region": ["IN", "US"], "min_deposit": 100000, "tenure_months": 12}

    # Status and tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    # Statistics
    total_recipients = models.IntegerField(default=0)
    total_sent = models.IntegerField(default=0)
    total_delivered = models.IntegerField(default=0)
    total_opened = models.IntegerField(default=0)
    total_failed = models.IntegerField(default=0)

    # Creator and timestamps
    created_by = models.CharField(max_length=100, default='ADMIN')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    scheduled_at = models.DateTimeField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)

    # Additional settings
    sender_email = models.EmailField(default='noreply@bankpoc.com')
    sender_name = models.CharField(max_length=200, default='Bank POC')
    reply_to_email = models.EmailField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['template_type']),
        ]

    def __str__(self):
        return f"Campaign: {self.name} - {self.status}"

    def get_recipient_count(self):
        """Calculate number of recipients based on filters."""
        from django.db.models import Q
        # This would query FD records based on target_filters
        # Placeholder implementation
        return self.total_recipients


class EmailCampaignLog(models.Model):
    """Model for tracking individual email delivery status."""

    DELIVERY_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SENT', 'Sent'),
        ('DELIVERED', 'Delivered'),
        ('OPENED', 'Opened'),
        ('CLICKED', 'Clicked'),
        ('BOUNCED', 'Bounced'),
        ('FAILED', 'Failed'),
    ]

    campaign = models.ForeignKey(
        EmailCampaign,
        on_delete=models.CASCADE,
        related_name='logs'
    )

    # Recipient information
    recipient_email = models.EmailField()
    recipient_name = models.CharField(max_length=200, blank=True, null=True)

    # Email content (personalized)
    subject = models.CharField(max_length=300)
    content = models.TextField()

    # Delivery tracking
    delivery_status = models.CharField(
        max_length=20,
        choices=DELIVERY_STATUS_CHOICES,
        default='PENDING'
    )
    failure_reason = models.TextField(blank=True, null=True)

    # Tracking timestamps
    queued_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    opened_at = models.DateTimeField(blank=True, null=True)
    clicked_at = models.DateTimeField(blank=True, null=True)

    # Tracking tokens
    tracking_token = models.CharField(max_length=100, unique=True, editable=False)

    # Additional metadata
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-queued_at']
        indexes = [
            models.Index(fields=['campaign', 'delivery_status']),
            models.Index(fields=['recipient_email']),
            models.Index(fields=['tracking_token']),
        ]

    def __str__(self):
        return f"Email to {self.recipient_email} - {self.delivery_status}"

    def save(self, *args, **kwargs):
        if not self.tracking_token:
            import uuid
            self.tracking_token = uuid.uuid4().hex[:32]
        super().save(*args, **kwargs)


# =============================================================================
# DATABASE QUERY LOG MODEL (Admin Query Interface Audit Trail)
# =============================================================================

class DatabaseQueryLog(models.Model):
    """Model for auditing admin database queries - audit trail for natural language queries."""
    
    STATUS_CHOICES = [
        ('SUCCESS', 'Success'),
        ('ERROR', 'Error'),
        ('TIMEOUT', 'Timeout'),
        ('BLOCKED', 'Blocked - Safety Check Failed'),
    ]
    
    # Query metadata
    query_text = models.TextField(help_text="Natural language query from user")
    sql_generated = models.TextField(blank=True, null=True, help_text="Generated SQL query")
    
    # Results
    result_summary = models.JSONField(blank=True, null=True, help_text="Summary of query results")
    result_count = models.IntegerField(default=0, help_text="Number of rows returned")
    row_limit_applied = models.IntegerField(default=1000, help_text="Max rows allowed")
    
    # Execution info
    executed_by = models.CharField(max_length=100, default='ADMIN', help_text="Admin username")
    executed_at = models.DateTimeField(auto_now_add=True)
    execution_time_ms = models.IntegerField(blank=True, null=True, help_text="Query execution time in ms")
    
    # Status and errors
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SUCCESS')
    error_message = models.TextField(blank=True, null=True)
    
    # Security
    is_read_only = models.BooleanField(default=True, help_text="Was this a read-only query?")
    sensitive_data_masked = models.BooleanField(default=False, help_text="Was sensitive data masked?")
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    
    # Export info
    exported_as = models.CharField(max_length=10, blank=True, null=True, help_text="CSV, JSON, or empty")
    
    class Meta:
        ordering = ['-executed_at']
        indexes = [
            models.Index(fields=['status', 'executed_at']),
            models.Index(fields=['executed_by', 'executed_at']),
            models.Index(fields=['is_read_only', 'executed_at']),
        ]
    
    def __str__(self):
        status_icon = '✓' if self.status == 'SUCCESS' else '✗'
        return f"{status_icon} {self.query_text[:50]}... ({self.status})"
    
    def get_duration_seconds(self):
        """Calculate query duration in seconds if available."""
        if self.execution_time_ms:
            return self.execution_time_ms / 1000
        return None

