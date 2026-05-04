// Main JavaScript for Bank POC Agentic AI

// EMI Calculator functionality
function calculateEMI() {
    const loanAmount = parseFloat(document.getElementById('loan_amount')?.value) || 0;
    const interestRate = parseFloat(document.getElementById('interest_rate')?.value) || 0;
    const tenureMonths = parseInt(document.getElementById('tenure_months')?.value) || 0;
    const method = document.getElementById('emi_method')?.value || 'Reducing Balance';
    const processingFee = parseFloat(document.getElementById('processing_fee')?.value) || 0;

    if (loanAmount <= 0 || interestRate <= 0 || tenureMonths <= 0) {
        showError('Please enter valid positive values for all fields.');
        return;
    }

    let monthlyRate, emi, totalInterest;

    if (method === 'Reducing Balance') {
        monthlyRate = interestRate / 12 / 100;
        emi = loanAmount * monthlyRate * Math.pow(1 + monthlyRate, tenureMonths) / (Math.pow(1 + monthlyRate, tenureMonths) - 1);
        totalInterest = (emi * tenureMonths) - loanAmount;
    } else if (method === 'Flat Rate') {
        totalInterest = loanAmount * (interestRate / 100) * (tenureMonths / 12);
        emi = (loanAmount + totalInterest) / tenureMonths;
    } else if (method === 'Compound Interest') {
        monthlyRate = interestRate / 12 / 100;
        const amount = loanAmount * Math.pow(1 + monthlyRate, tenureMonths);
        totalInterest = amount - loanAmount;
        emi = amount / tenureMonths;
    }

    const totalCost = loanAmount + totalInterest + processingFee;

    // Update display
    document.getElementById('monthly_emi_display').textContent = formatCurrency(emi);
    document.getElementById('total_interest_display').textContent = formatCurrency(totalInterest);
    document.getElementById('total_cost_display').textContent = formatCurrency(totalCost);
    document.getElementById('processing_fee_display').textContent = formatCurrency(processingFee);

    // Update donut chart
    updateDonutChart(loanAmount, totalInterest);

    // Generate amortization schedule
    generateAmortizationSchedule(loanAmount, interestRate, tenureMonths, method, emi);
}

// Get currency symbol from user region or default to ₹
function getCurrencySymbol() {
    if (window.USER_REGION && window.USER_REGION.currency) {
        return window.USER_REGION.currency;
    }
    // Fallback to cookie parsing
    const savedRegion = document.cookie.split('; ').find(row => row.startsWith('user_region='));
    if (savedRegion) {
        try {
            const region = JSON.parse(decodeURIComponent(savedRegion.split('=')[1]));
            return region.currency || '₹';
        } catch (e) {
            console.warn('Could not parse saved region:', e);
        }
    }
    return '₹';
}

function formatCurrency(amount) {
    const symbol = getCurrencySymbol();
    // Use en-IN locale for Indian format, en-US for US format
    if (symbol === '$' || symbol === '€' || symbol === '£') {
        return symbol + amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return symbol + amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function updateDonutChart(principal, interest) {
    const total = principal + interest;
    const principalPercent = (principal / total) * 100;
    const interestPercent = (interest / total) * 100;

    const principalOffset = 364 * (1 - principalPercent / 100);
    const interestOffset = 364 * (1 - interestPercent / 100);

    document.querySelector('.donut-principal').style.strokeDashoffset = principalOffset;
    document.querySelector('.donut-interest').style.strokeDashoffset = interestOffset;
}

function generateAmortizationSchedule(principal, annualRate, months, method, emi) {
    const scheduleTable = document.getElementById('amortization_schedule_body');
    if (!scheduleTable) return;

    scheduleTable.innerHTML = '';

    let remainingBalance = principal;
    const monthlyRate = annualRate / 12 / 100;

    for (let month = 1; month <= months; month++) {
        let interestPayment, principalPayment;

        if (method === 'Reducing Balance') {
            interestPayment = remainingBalance * monthlyRate;
            principalPayment = emi - interestPayment;
        } else if (method === 'Flat Rate') {
            interestPayment = emi * 0.3;
            principalPayment = emi - interestPayment;
        } else {
            interestPayment = remainingBalance * monthlyRate;
            principalPayment = emi - interestPayment;
        }

        if (principalPayment > remainingBalance) {
            principalPayment = remainingBalance;
        }

        remainingBalance -= principalPayment;

        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${month}</td>
            <td>${formatCurrency(remainingBalance + principalPayment)}</td>
            <td class="col-green">${formatCurrency(principalPayment)}</td>
            <td class="col-red">${formatCurrency(interestPayment)}</td>
            <td>${formatCurrency(principalPayment + interestPayment)}</td>
            <td>${formatCurrency(Math.max(0, remainingBalance))}</td>
        `;
        scheduleTable.appendChild(row);

        if (remainingBalance <= 0) break;
    }
}

function showError(message) {
    const errorDiv = document.getElementById('error_message');
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
        setTimeout(() => {
            errorDiv.style.display = 'none';
        }, 5000);
    }
}

// DTI Calculator
function calculateDTI() {
    const monthlyIncome = parseFloat(document.getElementById('monthly_income')?.value) || 0;
    const monthlyDebt = parseFloat(document.getElementById('monthly_debt')?.value) || 0;

    if (monthlyIncome <= 0) {
        showError('Please enter a valid monthly income.');
        return;
    }

    const dtiRatio = (monthlyDebt / monthlyIncome) * 100;
    document.getElementById('dti_result').textContent = dtiRatio.toFixed(2) + '%';

    // Color code the result
    const dtiBadge = document.getElementById('dti_badge');
    if (dtiRatio <= 35) {
        dtiBadge.style.color = 'var(--green)';
    } else if (dtiRatio <= 50) {
        dtiBadge.style.color = 'var(--amber)';
    } else {
        dtiBadge.style.color = 'var(--red)';
    }
}

// Tab switching
function switchTab(tabId) {
    // Hide all pages
    document.querySelectorAll('.page').forEach(page => {
        page.classList.remove('active');
    });

    // Remove active class from all pills
    document.querySelectorAll('.pill').forEach(pill => {
        pill.classList.remove('active');
    });

    // Show selected page
    const selectedPage = document.getElementById(tabId);
    if (selectedPage) {
        selectedPage.classList.add('active');
    }

    // Add active class to clicked pill
    event.target.classList.add('active');
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Show home page by default
    const homePage = document.getElementById('home');
    if (homePage) {
        homePage.classList.add('active');
    }

    // Set first pill as active
    const firstPill = document.querySelector('.pill');
    if (firstPill) {
        firstPill.classList.add('active');
    }
});

// ============================================================================
// COMPREHENSIVE UI ENHANCEMENTS
// ============================================================================

// Ripple Effect Implementation
function initRippleEffects() {
const rippleButtons = document.querySelectorAll('.btn-primary, .btn-admin, .pill, button:not(.no-ripple)');

rippleButtons.forEach(button => {
  if (button.hasAttribute('data-ripple-initialized')) return;
  button.setAttribute('data-ripple-initialized', 'true');
  
  button.addEventListener('click', function(e) {
    const rect = button.getBoundingClientRect();
    const ripple = document.createElement('span');
    ripple.classList.add('ripple');
    
    const size = Math.max(rect.width, rect.height);
    ripple.style.width = ripple.style.height = size + 'px';
    ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
    ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
    
    // Remove existing ripple
    const existingRipple = button.querySelector('.ripple');
    if (existingRipple) {
      existingRipple.remove();
    }
    
    button.appendChild(ripple);
    
    // Remove ripple after animation
    setTimeout(() => {
      ripple.remove();
    }, 600);
  });
});
}

// Toast Notification System
function showToast(message, type = 'info') {
// Remove existing toast if any
const existingToast = document.querySelector('.toast');
if (existingToast) {
  existingToast.remove();
}

const toast = document.createElement('div');
toast.classList.add('toast', `toast-${type}`);

let icon = '';
switch(type) {
  case 'success':
    icon = '✓';
    break;
  case 'error':
    icon = '✗';
    break;
  case 'warning':
    icon = '⚠';
    break;
  default:
    icon = 'ℹ';
}

toast.innerHTML = `
  <span class="toast-icon">${icon}</span>
  <span class="toast-message">${message}</span>
`;

document.body.appendChild(toast);

// Trigger animation
setTimeout(() => {
  toast.classList.add('toast-show');
}, 10);

// Auto-remove after 4 seconds
setTimeout(() => {
  toast.classList.remove('toast-show');
  setTimeout(() => {
    toast.remove();
  }, 300);
}, 4000);
}

// Floating Labels Implementation
function initFloatingLabels() {
const floatingInputs = document.querySelectorAll('.floating-label-input');

floatingInputs.forEach(input => {
  if (input.hasAttribute('data-floating-initialized')) return;
  input.setAttribute('data-floating-initialized', 'true');
  
  // Check if input has value on load
  if (input.value) {
    input.classList.add('has-content');
  }
  
  // Add event listeners
  input.addEventListener('focus', function() {
    this.classList.add('has-focus');
  });
  
  input.addEventListener('blur', function() {
    if (!this.value) {
      this.classList.remove('has-content');
    }
    this.classList.remove('has-focus');
  });
  
  input.addEventListener('input', function() {
    if (this.value) {
      this.classList.add('has-content');
    } else {
      this.classList.remove('has-content');
    }
  });
});
}

// Skeleton Loader Utility Functions
function createSkeletonLoader(type = 'text') {
const skeleton = document.createElement('div');
skeleton.classList.add('skeleton');

switch(type) {
  case 'text':
    skeleton.classList.add('skeleton-text');
    break;
  case 'card':
    skeleton.classList.add('skeleton-card');
    break;
  case 'avatar':
    skeleton.classList.add('skeleton-avatar');
    break;
  case 'line':
    skeleton.classList.add('skeleton-line');
    break;
}

return skeleton;
}

function showSkeleton(containerId, type = 'text', count = 1) {
const container = document.getElementById(containerId);
if (!container) return;

container.innerHTML = '';

for (let i = 0; i < count; i++) {
  container.appendChild(createSkeletonLoader(type));
}
}

function hideSkeleton(containerId, content) {
const container = document.getElementById(containerId);
if (!container) return;

if (content) {
  container.innerHTML = content;
} else {
  container.innerHTML = '';
}
}

// Loading Overlay Functions
function showLoadingOverlay(message = 'Loading...') {
const overlay = document.createElement('div');
overlay.id = 'loading-overlay';
overlay.classList.add('loading-overlay');
overlay.innerHTML = `
  <div class="loading-spinner"></div>
  <p class="loading-message">${message}</p>
`;
document.body.appendChild(overlay);
setTimeout(() => overlay.classList.add('loading-show'), 10);
}

function hideLoadingOverlay() {
const overlay = document.getElementById('loading-overlay');
if (overlay) {
  overlay.classList.remove('loading-show');
  setTimeout(() => overlay.remove(), 300);
}
}

// Dropdown Menu Toggle
function initDropdowns() {
const dropdownToggles = document.querySelectorAll('.pill-dropdown-toggle');

dropdownToggles.forEach(toggle => {
  if (toggle.hasAttribute('data-dropdown-initialized')) return;
  toggle.setAttribute('data-dropdown-initialized', 'true');
  
  toggle.addEventListener('click', function(e) {
    e.preventDefault();
    e.stopPropagation();
    
    const content = this.nextElementSibling;
    const isOpen = content.classList.contains('dropdown-open');
    
    // Close all other dropdowns
    document.querySelectorAll('.pill-dropdown-content').forEach(c => {
      c.classList.remove('dropdown-open');
    });
    
    // Toggle current dropdown
    if (!isOpen) {
      content.classList.add('dropdown-open');
    }
  });
});

// Close dropdowns when clicking outside
document.addEventListener('click', function() {
  document.querySelectorAll('.pill-dropdown-content').forEach(c => {
    c.classList.remove('dropdown-open');
  });
});
}

// Enhanced Form Validation
function validateForm(formId) {
const form = document.getElementById(formId);
if (!form) return false;

const inputs = form.querySelectorAll('input[required], select[required], textarea[required]');
let isValid = true;

inputs.forEach(input => {
  if (!input.value || input.value.trim() === '') {
    isValid = false;
    input.classList.add('input-error');
    
    // Show error toast
    const label = input.previousElementSibling?.textContent || input.getAttribute('placeholder') || 'This field';
    showToast(`${label} is required`, 'error');
  } else {
    input.classList.remove('input-error');
  }
});

return isValid;
}

// Initialize all UI enhancements
function initUIEnhancements() {
initRippleEffects();
initFloatingLabels();
initDropdowns();

// Re-initialize ripples after AJAX content loads
document.addEventListener('ajaxComplete', initRippleEffects);
document.addEventListener('ajaxComplete', initFloatingLabels);
}

// Initialize on page load
if (document.readyState === 'loading') {
document.addEventListener('DOMContentLoaded', initUIEnhancements);
} else {
initUIEnhancements();
}
