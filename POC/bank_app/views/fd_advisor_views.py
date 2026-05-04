"""
FD Advisor and TD/FD Creation Views.
Contains endpoints for Fixed Deposit rates, creation, and related operations.
"""

import os
import json
import logging
import calendar
import traceback
import re
from datetime import datetime, timedelta
from decimal import Decimal

import markdown

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone

from .base import logger

logger = logging.getLogger(__name__)

# Currency symbol mapping for region-aware formatting
CURRENCY_SYMBOLS = {
    'INR': '₹', 'USD': '$', 'GBP': '£', 'CAD': '$', 'AUD': '$',
    'EUR': '€', 'JPY': '¥', 'CNY': '¥', 'CHF': 'Fr', 'MXN': '$',
    'BRL': 'R$', 'KRW': '₩', 'RUB': '₽',
    # Country code to currency symbol fallback
    'IN': '₹', 'US': '$', 'GB': '£', 'CA': '$', 'AU': '$',
    'DE': '€', 'FR': '€', 'JP': '¥', 'CN': '¥', 'BR': 'R$',
    'MX': '$', 'KR': '₩', 'RU': '₽',
}

def get_currency_symbol_for_region(region):
    """
    Get currency symbol based on region/country code or name.
    
    Args:
        region: Region name or country code (e.g., 'India', 'IN', 'United States', 'US')
    
    Returns:
        Currency symbol string
    """
    if not region:
        return '₹'  # Default to INR
    
    region_upper = region.upper()
    
    # Check if it's a currency code first
    if region_upper in CURRENCY_SYMBOLS:
        return CURRENCY_SYMBOLS[region_upper]
    
    # Check country code mapping
    if region_upper in CURRENCY_SYMBOLS:
        return CURRENCY_SYMBOLS[region_upper]
    
    # Map region names to currency codes
    region_to_currency = {
        'INDIA': 'INR', 'IN': 'INR',
        'UNITED STATES': 'USD', 'US': 'USD', 'AMERICA': 'USD',
        'UNITED KINGDOM': 'GBP', 'GB': 'GBP', 'UK': 'GBP',
        'CANADA': 'CAD', 'CA': 'CAD',
        'AUSTRALIA': 'AUD', 'AU': 'AUD',
        'GERMANY': 'EUR', 'DE': 'EUR',
        'FRANCE': 'EUR', 'FR': 'EUR',
        'JAPAN': 'JPY', 'JP': 'JPY',
        'CHINA': 'CNY', 'CN': 'CNY',
        'BRAZIL': 'BRL', 'BR': 'BRL',
        'MEXICO': 'MXN', 'MX': 'MXN',
        'SOUTH KOREA': 'KRW', 'KR': 'KRW',
        'RUSSIA': 'RUB', 'RU': 'RUB',
    }
    
    currency_code = region_to_currency.get(region_upper, 'USD')
    return CURRENCY_SYMBOLS.get(currency_code, '$')


# =============================================================================
# FD RATES API
# =============================================================================

@csrf_exempt
def fd_rates_api(request):
    """
    FD/Product rates API endpoint.

    POST /api/fd-rates/
    Body: {
        "region": "India",
        "product_type": "FD"  # FD, RD, PPF, MF, NPS, SGB, BOND, TBILL, CD
    }
    Returns: List of rates from various providers based on product type
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        region = data.get('region', 'India')
        product_type = data.get('product_type', 'FD')

        # Get rates based on product type
        rates = get_product_rates(product_type, region)

        return JsonResponse({'rates': rates, 'region': region, 'product_type': product_type})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_product_rates(product_type, region):
    """
    Get rates for a specific financial product type.

    Args:
        product_type: Product code (FD, RD, PPF, MF, NPS, SGB, BOND, TBILL, CD)
        region: Region/Country

    Returns:
        List of rate dictionaries
    """
    is_india = region in ['India', 'IN', 'INR']

    # India-specific rates
    india_rates = {
        'FD': [
            {'provider': 'HDFC Bank', 'rate': 7.2, 'tenure': '12-15 months', 'min_deposit': 10000, 'type': 'Private Bank'},
            {'provider': 'ICICI Bank', 'rate': 7.1, 'tenure': '12-18 months', 'min_deposit': 10000, 'type': 'Private Bank'},
            {'provider': 'SBI', 'rate': 7.0, 'tenure': '12-23 months', 'min_deposit': 1000, 'type': 'Public Bank'},
            {'provider': 'Axis Bank', 'rate': 7.15, 'tenure': '12-15 months', 'min_deposit': 10000, 'type': 'Private Bank'},
            {'provider': 'Kotak Mahindra', 'rate': 7.25, 'tenure': '12-18 months', 'min_deposit': 10000, 'type': 'Private Bank'},
            {'provider': 'IDFC First', 'rate': 7.4, 'tenure': '12-15 months', 'min_deposit': 1000, 'type': 'Private Bank'},
        ],
        'RD': [
            {'provider': 'HDFC Bank', 'rate': 7.25, 'tenure': '12-15 months', 'min_deposit': 1000, 'type': 'Private Bank'},
            {'provider': 'ICICI Bank', 'rate': 7.20, 'tenure': '12-18 months', 'min_deposit': 1000, 'type': 'Private Bank'},
            {'provider': 'SBI', 'rate': 7.10, 'tenure': '12-24 months', 'min_deposit': 1000, 'type': 'Public Bank'},
            {'provider': 'Axis Bank', 'rate': 7.25, 'tenure': '12-15 months', 'min_deposit': 1000, 'type': 'Private Bank'},
            {'provider': 'Kotak Mahindra', 'rate': 7.30, 'tenure': '12-18 months', 'min_deposit': 1000, 'type': 'Private Bank'},
        ],
        'PPF': [
            {'provider': 'Government of India (PPF)', 'rate': 7.1, 'tenure': '15 years', 'min_deposit': 500, 'type': 'Government', 'tax_benefit': '80C, Tax-free'},
        ],
        'MF': [
            {'provider': 'SBI Mutual Fund', 'rate': 12.5, 'tenure': '5+ years', 'min_deposit': 500, 'type': 'Mutual Fund', 'category': 'Equity'},
            {'provider': 'HDFC Mutual Fund', 'rate': 12.8, 'tenure': '5+ years', 'min_deposit': 500, 'type': 'Mutual Fund', 'category': 'Equity'},
            {'provider': 'ICICI Prudential', 'rate': 12.3, 'tenure': '5+ years', 'min_deposit': 500, 'type': 'Mutual Fund', 'category': 'Equity'},
            {'provider': 'Axis Mutual Fund', 'rate': 12.6, 'tenure': '5+ years', 'min_deposit': 500, 'type': 'Mutual Fund', 'category': 'Equity'},
            {'provider': 'Kotak Mahindra MF', 'rate': 12.4, 'tenure': '5+ years', 'min_deposit': 500, 'type': 'Mutual Fund', 'category': 'Equity'},
        ],
        'NPS': [
            {'provider': 'Government NPS', 'rate': 10.0, 'tenure': 'Until age 60', 'min_deposit': 500, 'type': 'Government', 'tax_benefit': '80C, 80CCD(1B)'},
        ],
        'SGB': [
            {'provider': 'Reserve Bank of India (SGB)', 'rate': 2.5, 'tenure': '8 years', 'min_deposit': '1 gram gold', 'type': 'Government', 'gold_exposure': True},
        ],
        'BOND': [
            {'provider': 'HDFC Corporate Bonds', 'rate': 8.5, 'tenure': '3-5 years', 'min_deposit': 10000, 'type': 'Corporate', 'rating': 'AAA'},
            {'provider': 'ICICI Corporate Bonds', 'rate': 8.3, 'tenure': '3-5 years', 'min_deposit': 10000, 'type': 'Corporate', 'rating': 'AAA'},
            {'provider': 'SBI Corporate Bonds', 'rate': 8.2, 'tenure': '3-5 years', 'min_deposit': 10000, 'type': 'Public', 'rating': 'AAA'},
            {'provider': 'Axis Corporate Bonds', 'rate': 8.4, 'tenure': '3-5 years', 'min_deposit': 10000, 'type': 'Corporate', 'rating': 'AAA'},
            {'provider': 'Kotak Corporate Bonds', 'rate': 8.6, 'tenure': '3-5 years', 'min_deposit': 10000, 'type': 'Corporate', 'rating': 'AAA'},
        ],
        'TBILL': [
            {'provider': 'RBI T-Bills', 'rate': 6.8, 'tenure': '364 days', 'min_deposit': 25000, 'type': 'Government', 'tenure_options': ['91', '182', '364']},
        ],
        'CD': [
            {'provider': 'HDFC Bank CD', 'rate': 7.3, 'tenure': '12-15 months', 'min_deposit': 10000, 'type': 'Private Bank'},
            {'provider': 'ICICI Bank CD', 'rate': 7.2, 'tenure': '12-18 months', 'min_deposit': 10000, 'type': 'Private Bank'},
            {'provider': 'SBI CD', 'rate': 7.1, 'tenure': '12-23 months', 'min_deposit': 10000, 'type': 'Public Bank'},
            {'provider': 'Axis Bank CD', 'rate': 7.25, 'tenure': '12-15 months', 'min_deposit': 10000, 'type': 'Private Bank'},
            {'provider': 'Kotak Mahindra CD', 'rate': 7.35, 'tenure': '12-18 months', 'min_deposit': 10000, 'type': 'Private Bank'},
        ],
    }

    # US rates (simplified)
    us_rates = {
        'FD': [
            {'provider': 'Chase', 'rate': 4.5, 'tenure': '12 months', 'min_deposit': 1000, 'type': 'Bank'},
            {'provider': 'Bank of America', 'rate': 4.75, 'tenure': '12 months', 'min_deposit': 1000, 'type': 'Bank'},
            {'provider': 'Wells Fargo', 'rate': 4.6, 'tenure': '12 months', 'min_deposit': 1000, 'type': 'Bank'},
            {'provider': 'Citibank', 'rate': 4.8, 'tenure': '12 months', 'min_deposit': 1000, 'type': 'Bank'},
            {'provider': 'Capital One', 'rate': 4.9, 'tenure': '12 months', 'min_deposit': 1000, 'type': 'Bank'},
            {'provider': 'TD Bank', 'rate': 4.7, 'tenure': '12 months', 'min_deposit': 1000, 'type': 'Bank'},
        ],
    }

    if is_india:
        return india_rates.get(product_type, india_rates['FD'])
    else:
        return us_rates.get(product_type, us_rates['FD'])
    
    
def generate_consistent_summary(product_type, rates, amount, tenure, tenure_unit, region, senior_citizen=False, crew_output=None):
    """
    Generate a consistent summary that matches the table data.
    If crew_output is provided, use the full agent output; otherwise fall back to simple summary.

    Args:
        product_type: Product code (FD, RD, etc.)
        rates: List of rate dictionaries from get_product_rates
        amount: Investment amount
        tenure: Tenure value
        tenure_unit: 'months', 'years', or 'days'
        region: Region name or country code
        senior_citizen: Whether user is senior citizen
        crew_output: Full CrewAI agent output (optional). If provided, this will be used as the summary.

    Returns:
        Dictionary with 'summary_markdown', 'structured_data', and 'full_agent_output' keys
    """
    # Get currency symbol for the region
    currency_symbol = get_currency_symbol_for_region(region)

    # Sort rates by rate descending (highest first)
    sorted_rates = sorted(rates, key=lambda x: x['rate'], reverse=True)

    # Get best option
    best = sorted_rates[0] if sorted_rates else None

    if not best:
        # If crew output is available, use it even if rates are empty
        if crew_output:
            return {
                'summary_markdown': crew_output if isinstance(crew_output, str) else str(crew_output),
                'structured_data': {'best_option': None, 'all_options': []},
                'full_agent_output': crew_output
            }
        return {
            'summary_markdown': 'No rates available for this product.',
            'structured_data': {'best_option': None, 'all_options': []},
            'full_agent_output': None
        }

    # Calculate maturity amount for best option
    rate_decimal = best['rate'] / 100
    min_deposit = best.get('min_deposit', 10000)

    # Adjust rate for senior citizen if applicable
    adjusted_rate = best['rate']
    if senior_citizen and product_type == 'FD':
        adjusted_rate += 0.50

    # Calculate maturity based on tenure unit
    if tenure_unit == 'years':
        tenure_months = tenure * 12
    elif tenure_unit == 'days':
        tenure_months = tenure / 30
    else:
        tenure_months = tenure

    maturity_amount = amount * pow(1 + adjusted_rate / 100 / 12, tenure_months)
    interest_earned = maturity_amount - amount

    # Generate markdown summary that matches table data
    product_names = {
        'FD': 'Fixed Deposit',
        'RD': 'Recurring Deposit',
        'PPF': 'Public Provident Fund',
        'MF': 'Mutual Fund',
        'NPS': 'National Pension System',
        'SGB': 'Sovereign Gold Bond',
        'BOND': 'Corporate Bond',
        'TBILL': 'Treasury Bill',
        'CD': 'Certificate of Deposit'
    }
    product_name = product_names.get(product_type, product_type)

    summary_md = f"""**Best {product_name} Option:**

| Provider | Rate | Min Deposit | Maturity Amount |
|----------|------|-------------|-----------------|
| {best['provider']} | {adjusted_rate}% | {currency_symbol}{min_deposit:,} | {currency_symbol}{maturity_amount:,.0f} |

**Investment Summary:**
- **Investment Amount:** {currency_symbol}{amount:,}
- **Interest Rate:** {adjusted_rate}%
- **Tenure:** {tenure} {tenure_unit}
- **Estimated Maturity:** {currency_symbol}{maturity_amount:,.0f}
- **Interest Earned:** {currency_symbol}{interest_earned:,.0f}

**Ranking:** {best['provider']} is ranked **#1** with the highest rate of {adjusted_rate}%.
"""
    
    # Build structured data for table
    structured_data = {
        'best_option': {
            'provider': best['provider'],
            'rate': adjusted_rate,
            'min_deposit': min_deposit,
            'tenure': best.get('tenure', f'{tenure} {tenure_unit}'),
            'maturity_amount': round(maturity_amount, 2),
            'interest_earned': round(interest_earned, 2)
        },
        'all_options': []
    }
    
    for idx, rate_data in enumerate(sorted_rates, 1):
        r = rate_data['rate']
        if senior_citizen and product_type == 'FD':
            r += 0.50
        
        r_maturity = amount * pow(1 + r / 100 / 12, tenure_months)
        r_interest = r_maturity - amount
        
        structured_data['all_options'].append({
            'rank': idx,
            'provider': rate_data['provider'],
            'rate': r,
            'tenure': rate_data.get('tenure', f'{tenure} {tenure_unit}'),
            'min_deposit': rate_data.get('min_deposit', 10000),
            'maturity_amount': round(r_maturity, 2),
            'interest_earned': round(r_interest, 2)
        })
    
    # If crew output is available, prefer it over the simple summary
    if crew_output:
        crew_output_str = crew_output if isinstance(crew_output, str) else str(crew_output)
        return {
            'summary_markdown': crew_output_str,
            'structured_data': structured_data,
            'full_agent_output': crew_output_str
        }
    
    return {
        'summary_markdown': summary_md,
        'structured_data': structured_data,
        'full_agent_output': None
    }


def extract_risk_analysis_from_crew_output(crew_output) -> dict:
    """
    Extract structured risk analysis data from CrewAI agent output.
    
    Args:
        crew_output: Full markdown output from the CrewAI agent (string or dict)
        
    Returns:
        Dictionary with extracted risk analysis components:
        - risk_matrix: List of provider risk assessments
        - safety_profiles: Safety profile for each provider
        - insurance_status: DICGC insurance status
        - credit_risks: Credit risk assessments
        - recent_news: Recent news affecting providers
        - overall_summary: Overall risk summary
        - raw_risk_section: Raw risk section markdown
    """
    # Convert to string if needed
    if isinstance(crew_output, dict):
        crew_output = crew_output.get('raw', str(crew_output))
    elif not isinstance(crew_output, str):
        crew_output = str(crew_output) if crew_output else ''
    
    if not crew_output:
        return {
            'risk_matrix': [],
            'safety_profiles': [],
            'insurance_status': [],
            'credit_risks': [],
            'recent_news': [],
            'overall_summary': '',
            'raw_risk_section': '',
            'has_risk_data': False
        }
    
    result = {
        'risk_matrix': [],
        'safety_profiles': [],
        'insurance_status': [],
        'credit_risks': [],
        'recent_news': [],
        'overall_summary': '',
        'raw_risk_section': '',
        'has_risk_data': False
    }
    
    # Extract risk matrix table if present
    risk_matrix_pattern = r'##?\s*.*?Risk.*?Matrix.*?\n(.*?\|.*?\|.*?\|.*?\|.*?\n(?:\|.*?\|.*?\|.*?\|.*?\|.*?\n)+)'
    risk_matrix_match = re.search(risk_matrix_pattern, crew_output, re.IGNORECASE | re.DOTALL)
    
    if risk_matrix_match:
        result['has_risk_data'] = True
        result['raw_risk_section'] = risk_matrix_match.group(0)
        
        # Parse table rows
        table_content = risk_matrix_match.group(1)
        rows = table_content.split('\n')
        for row in rows:
            if '|' in row:
                cells = [cell.strip() for cell in row.split('|')[1:-1]]  # Remove first/empty cells
                if len(cells) >= 4:
                    result['risk_matrix'].append({
                        'provider': cells[0],
                        'credit_risk': cells[1] if len(cells) > 1 else 'N/A',
                        'market_risk': cells[2] if len(cells) > 2 else 'N/A',
                        'liquidity_risk': cells[3] if len(cells) > 3 else 'N/A',
                        'overall_safety': cells[4] if len(cells) > 4 else 'N/A'
                    })
    
    # Extract safety profiles (look for provider sections with safety classification)
    safety_pattern = r'###?\s*(?:Provider|Bank|Institution)\s*[:\s]+([^\n]+).*?Safety[:\s]+([^\n]+)'
    safety_matches = re.findall(safety_pattern, crew_output, re.IGNORECASE)
    for match in safety_matches:
        result['safety_profiles'].append({
            'provider': match[0].strip(),
            'safety_level': match[1].strip()
        })
    
    # Extract DICGC/insurance status
    insurance_pattern = r'(?:DICGC|Insurance|Insured)\s*[:\s]+([^\n]+)'
    insurance_matches = re.findall(insurance_pattern, crew_output, re.IGNORECASE)
    for match in insurance_matches:
        result['insurance_status'].append(match.strip())
    
    # Extract credit risk assessments
    credit_risk_pattern = r'(?:Credit\s*Risk|Credit\s*Rating)\s*[:\s]+([^\n]+)'
    credit_risk_matches = re.findall(credit_risk_pattern, crew_output, re.IGNORECASE)
    for match in credit_risk_matches:
        result['credit_risks'].append(match.strip())
    
    # Extract recent news sections
    news_pattern = r'##?\s*Recent\s*News.*?\n((?:-?\s*\*\*.*?\*\*.*?\n?)+)'
    news_match = re.search(news_pattern, crew_output, re.IGNORECASE)
    if news_match:
        result['has_risk_data'] = True
        news_text = news_match.group(1)
        # Parse individual news items
        news_items = re.findall(r'-?\s*\*\*(.+?)\*\*[:\s-]*(.+?)(?:\n|$)', news_text)
        for headline, summary in news_items:
            result['recent_news'].append({
                'headline': headline.strip(),
                'summary': summary.strip()
            })
    
    # Extract overall risk summary
    summary_pattern = r'##?\s*(?:Overall\s*)?Risk\s*(?:Summary|Assessment|Overview).*?\n((?:.*?\n)*?)(?=\n##|\Z)'
    summary_match = re.search(summary_pattern, crew_output, re.IGNORECASE)
    if summary_match:
        result['overall_summary'] = summary_match.group(1).strip()
        result['has_risk_data'] = True
    
    # If no structured data found, try to extract any risk-related section
    if not result['has_risk_data']:
        risk_section = re.search(r'(##?\s*Risk.*?\n(?:.*?\n)*?)(?=\n##|\Z)', crew_output, re.IGNORECASE)
        if risk_section:
            result['raw_risk_section'] = risk_section.group(1)
            result['has_risk_data'] = True
    
    return result


# =============================================================================
# NEW: Product Analysis API Endpoint
# =============================================================================

@csrf_exempt
def product_analysis_api(request):
    """
    Generic product analysis endpoint for all financial products.

    POST /api/product-analysis/
Body: {
    "product_type": "FD",  # FD, RD, PPF, MF, NPS, SGB, BOND, TBILL, CD
    "amount": 500000,
    "tenure": 12,
    "tenure_unit": "months",  # months, years, days
    "region": "India",
    # Product-specific fields:
    "senior_citizen": false,     # For FD
    "auto_renewal": true,        # For FD
    "monthly_contribution": 5000, # For RD
    "start_date": "2025-01-01",  # For RD
    "is_sip": true,              # For MF
    "risk_level": "moderate",    # For MF, NPS
    "age": 30,                   # For NPS
    "risk_profile": "moderate",  # For NPS
    "coupon_frequency": "semi-annual", # For Bonds
}

Returns: Analysis results from CrewAI
"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)

        # Validate required fields
        product_type = data.get('product_type', 'FD')
        amount = data.get('amount', 0)
        tenure = data.get('tenure', 12)
        region = data.get('region', 'India')

        if amount <= 0 or tenure <= 0:
            return JsonResponse({'error': 'Invalid amount or tenure'}, status=400)

        # Build user query based on product type
        product_names = {
            'FD': 'Fixed Deposit',
            'RD': 'Recurring Deposit',
            'PPF': 'Public Provident Fund',
            'MF': 'Mutual Fund',
            'NPS': 'National Pension System',
            'SGB': 'Sovereign Gold Bond',
            'BOND': 'Corporate Bond',
            'TBILL': 'Treasury Bill',
            'CD': 'Certificate of Deposit'
        }

        product_name = product_names.get(product_type, product_type)
        tenure_unit = data.get('tenure_unit', 'months')

        user_query = f"Analyze {product_name} rates for {region} with {tenure_unit} tenure of {tenure} {tenure_unit} and investment amount of {amount}."

        # Add product-specific context
        if product_type == 'FD':
            if data.get('senior_citizen'):
                user_query += " User is a senior citizen."
            if data.get('auto_renewal'):
                user_query += " Auto-renewal preferred."
        elif product_type == 'RD':
            user_query += f" Monthly contribution: {data.get('monthly_contribution', amount)}."
        elif product_type == 'MF':
            user_query += f" Risk level: {data.get('risk_level', 'moderate')}. SIP: {data.get('is_sip', True)}."
        elif product_type == 'NPS':
            user_query += f" Age: {data.get('age', 30)}. Risk profile: {data.get('risk_profile', 'moderate')}."
        elif product_type == 'BOND':
            user_query += f" Coupon frequency: {data.get('coupon_frequency', 'semi-annual')}."

        # Call CrewAI analysis
        logger.info(f"=== STARTING CrewAI analysis ===")
        logger.info(f"product_type={product_type}, region={region}, amount={amount}, tenure={tenure} {tenure_unit}")
        logger.info(f"User query: {user_query}")

        import sys
        from pathlib import Path

        # Get the absolute path to the Test/ directory (where crews.py is located)
        # __file__ = Test/bank_app/views/fd_advisor_views.py
        # parent.parent.parent = Test/
        test_dir = Path(__file__).resolve().parent.parent.parent
        test_dir_str = str(test_dir)

        logger.info(f"Test directory: {test_dir_str}")
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"Current sys.path (first 5): {sys.path[:5]}")

        # Add Test/ to sys.path if not already present
        if test_dir_str not in sys.path:
            sys.path.insert(0, test_dir_str)
            logger.info(f"Added {test_dir_str} to sys.path")

        # Verify the crews module can be found
        crews_path = test_dir / 'crews.py'
        if not crews_path.exists():
            error_msg = f"crews.py NOT FOUND at {crews_path}. sys.path: {sys.path[:5]}"
            logger.error(error_msg)
            raise ImportError(error_msg)

        logger.info(f"crews.py found at {crews_path}")

        # Verify agents.py and tasks.py exist too
        agents_path = test_dir / 'agents.py'
        tasks_path = test_dir / 'tasks.py'
        if not agents_path.exists():
            error_msg = f"agents.py NOT FOUND at {agents_path}"
            logger.error(error_msg)
            raise ImportError(error_msg)
        if not tasks_path.exists():
            error_msg = f"tasks.py NOT FOUND at {tasks_path}"
            logger.error(error_msg)
            raise ImportError(error_msg)

        logger.info("All required modules (crews.py, agents.py, tasks.py) found")

        try:
            from crews import run_analysis_crew
            logger.info("Successfully imported run_analysis_crew from crews module")
        except ImportError as import_err:
            error_msg = f"Failed to import run_analysis_crew: {import_err}"
            logger.error(error_msg)
            logger.error(f"sys.path: {sys.path[:5]}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise ImportError(error_msg) from import_err

        logger.info(f"Calling run_analysis_crew with user_query='{user_query[:100]}...', region={region}, product_type={product_type}")
        logger.info("This may take 10-30 seconds...")

        try:
            result = run_analysis_crew(user_query, region=region, product_type=product_type)
            logger.info("CrewAI analysis completed successfully")
        except Exception as crew_error:
            error_msg = f"CrewAI execution failed: {crew_error}"
            logger.error(error_msg)
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise RuntimeError(error_msg) from crew_error

        # Extract result - handle both CrewOutput objects and string results
        if hasattr(result, 'raw'):
            analysis_result = result.raw
        elif hasattr(result, 'dict'):
            analysis_result = result.dict()
        else:
            analysis_result = str(result)

        logger.info(f"Analysis result type: {type(analysis_result)}")

        # Get rates from get_product_rates for consistent summary
        rates = get_product_rates(product_type, region)

        # Generate consistent summary that matches table data
        # Pass the full crew output so the summary includes the complete agent analysis
        senior_citizen = data.get('senior_citizen', False) if product_type == 'FD' else False
        summary_data = generate_consistent_summary(
            product_type=product_type,
            rates=rates,
            amount=amount,
            tenure=tenure,
            tenure_unit=tenure_unit,
            region=region,
            senior_citizen=senior_citizen,
            crew_output=analysis_result  # Pass full crew output
        )
    
        # Render markdown to HTML using the markdown library with enhanced extensions
        # 'tables' preserves markdown tables, 'fenced_code' handles code blocks,
        # 'nl2br' converts newlines to <br>, 'extra' adds additional formatting
        summary_html = markdown.markdown(
            summary_data['summary_markdown'],
            extensions=['fenced_code', 'tables', 'nl2br', 'extra', 'codehilite']
        )
    
        # Extract risk analysis from crew output
        risk_analysis_data = extract_risk_analysis_from_crew_output(analysis_result)
        
        # Render risk analysis markdown to HTML if available
        risk_analysis_html = ''
        if risk_analysis_data['has_risk_data'] and risk_analysis_data['raw_risk_section']:
            risk_analysis_html = markdown.markdown(
                risk_analysis_data['raw_risk_section'],
                extensions=['fenced_code', 'tables', 'nl2br', 'extra', 'codehilite']
            )
        elif analysis_result:
            # Fallback: try to render the full agent output as risk analysis
            risk_analysis_html = markdown.markdown(
                str(analysis_result),
                extensions=['fenced_code', 'tables', 'nl2br', 'extra', 'codehilite']
            )
    
        return JsonResponse({
            'success': True,
            'product_type': product_type,
            'product_name': product_name,
            'amount': amount,
            'tenure': tenure,
            'tenure_unit': tenure_unit,
            'region': region,
            'result': analysis_result,
            'summary_markdown': summary_data['summary_markdown'],
            'summary_html': summary_html,
            'structured_data': summary_data['structured_data'],
            'full_agent_output': summary_data.get('full_agent_output', analysis_result),
            'risk_analysis': risk_analysis_html,  # Rendered HTML risk analysis
            'risk_analysis_data': risk_analysis_data,  # Structured risk data
        })

    except ImportError as import_err:
        error_msg = f"Failed to import CrewAI modules: {import_err}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        return JsonResponse({
            'error': str(import_err),
            'detail': 'CrewAI module import failed. Check server logs for details.'
        }, status=500)
    except Exception as e:
        error_msg = f"Unexpected error in product_analysis_api: {e}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        return JsonResponse({
            'error': str(e),
            'detail': 'An unexpected error occurred. Check server logs for details.'
        }, status=500)


# =============================================================================
# TD/FD CREATION API
# =============================================================================

@csrf_exempt
@require_POST
def td_fd_creation_api(request):
    """
    API endpoint for creating a Fixed/Term Deposit.

    This endpoint:
    1. Validates FD creation request data
    2. Creates FD record in database
    3. Generates FD certificate (PDF)
    4. Sends email notification with certificate attachment
    5. Returns FD details and certificate download URL

    POST /api/td-fd-creation/
    Body: {
        "bank_name": "HDFC Bank",
        "rate": 7.5,
        "amount": 500000,
        "tenure_months": 12,
        "start_date": "2025-05-01",
        "customer_name": "John Doe",
        "customer_email": "john@example.com",
        "customer_phone": "+91-9876543210",
        "senior_citizen": false,
        "auto_renewal": true,
        "send_email": true,
        "region": "IN"
    }
    """
    # Import models and utilities at function scope (outside try block)
    from ..models import FixedDeposit
    from ..fd_certificate_utils import generate_fd_certificate
    
    try:
        data = json.loads(request.body)

        # Validate required fields
        required_fields = ['bank_name', 'rate', 'amount', 'tenure_months', 'start_date']
        for field in required_fields:
            if field not in data:
                return JsonResponse({'error': f'{field} is required'}, status=400)

        # Parse and validate data
        bank_name = data['bank_name']
        rate = Decimal(str(data['rate']))
        amount = Decimal(str(data['amount']))
        tenure_months = int(data['tenure_months'])
        start_date_str = data['start_date']

        # Optional fields with defaults
        customer_name = data.get('customer_name', '')
        customer_email = data.get('customer_email', '')
        customer_phone = data.get('customer_phone', '')
        senior_citizen = data.get('senior_citizen', False)
        loan_against_fd = data.get('loan_against_fd', False)
        auto_renewal = data.get('auto_renewal', False)
        send_email = data.get('send_email', True)
        region = data.get('region', 'IN')
        user_session_id = request.session.session_key or 'anonymous'

        # Parse start date
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'error': 'Invalid start_date format. Use YYYY-MM-DD'}, status=400)

        # Calculate maturity date
        year_add = tenure_months // 12
        month_add = tenure_months % 12

        new_year = start_date.year + year_add
        new_month = start_date.month + month_add

        if new_month > 12:
            new_year += 1
            new_month -= 12

        try:
            maturity_date = start_date.replace(year=new_year, month=new_month)
        except ValueError:
            last_day = calendar.monthrange(new_year, new_month)[1]
            maturity_date = start_date.replace(year=new_year, month=new_month, day=last_day)

        # Calculate maturity amount and interest
        rate_decimal = float(rate) / 100
        principal = float(amount)
        maturity_amount = principal * pow(1 + rate_decimal / 12, tenure_months)
        interest_earned = maturity_amount - principal

        # Create FD record
        fd = FixedDeposit(
            bank_name=bank_name,
            rate=rate,
            amount=amount,
            tenure_months=tenure_months,
            start_date=start_date,
            maturity_date=maturity_date,
            maturity_amount=round(maturity_amount, 2),
            interest_earned=round(interest_earned, 2),
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            senior_citizen=senior_citizen,
            loan_against_fd=loan_against_fd,
            auto_renewal=auto_renewal,
            region=region,
            user_session_id=user_session_id,
            status='ACTIVE'
        )
        fd.save()

        logger.info(f"FD created: {fd.fd_id} for {customer_name}")

        # Generate certificate
        certificate_path = generate_fd_certificate(fd)
        if certificate_path:
            fd.certificate_path = certificate_path
            fd.certificate_generated = True
            fd.save()

        # Send email notification
        certificate_url = None
        email_sent = False
        if send_email and customer_email and certificate_path:
            email_sent = send_fd_confirmation_email(
                customer_email=customer_email,
                customer_name=customer_name,
                fd_instance=fd,
                certificate_path=certificate_path
            )
            fd.email_sent = email_sent
            if email_sent:
                fd.email_sent_at = timezone.now()
                fd.save()

        # Build certificate download URL
        if certificate_path:
            certificate_url = f"/media/{certificate_path}"
        else:
            certificate_url = None

        return JsonResponse({
            'success': True,
            'fd_id': fd.fd_id,
            'account_number': fd.account_number,
            'bank_name': fd.bank_name,
            'rate': float(fd.rate),
            'amount': float(fd.amount),
            'tenure_months': fd.tenure_months,
            'start_date': fd.start_date.strftime('%Y-%m-%d'),
            'maturity_date': fd.maturity_date.strftime('%Y-%m-%d'),
            'maturity_amount': float(fd.maturity_amount),
            'interest_earned': float(fd.interest_earned),
            'certificate_generated': fd.certificate_generated,
            'certificate_url': certificate_url,
            'email_sent': email_sent,
            'status': fd.status
        })

    except FixedDeposit.DoesNotExist:
        return JsonResponse({'error': 'FD not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"FD creation error: {e}")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


def send_fd_confirmation_email(customer_email, customer_name, fd_instance, certificate_path):
    """
    Send FD confirmation email with certificate attachment.

    Args:
        customer_email: Customer's email address
        customer_name: Customer's name
        fd_instance: FixedDeposit model instance
        certificate_path: Path to the certificate PDF file

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        # Build full certificate path
        full_certificate_path = os.path.join(settings.MEDIA_ROOT, certificate_path)

        if not os.path.exists(full_certificate_path):
            logger.warning(f"Certificate file not found: {full_certificate_path}")
            return False

        # Email subject
        subject = f"Your Fixed Deposit Certificate - {fd_instance.fd_id}"

        # Email body (HTML)
        html_content = f"""
<html>
<head>
<style>
body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
.container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
.content {{ background: #f9f9f9; padding: 20px; }}
.fd-details {{ background: white; padding: 15px; border-radius: 8px; margin: 15px 0; }}
.fd-details h3 {{ color: #c9a84c; margin-top: 0; }}
.fd-details table {{ width: 100%; border-collapse: collapse; }}
.fd-details td {{ padding: 8px; border-bottom: 1px solid #eee; }}
.fd-details td:first-child {{ font-weight: bold; color: #555; }}
.footer {{ background: #1a1a2e; color: white; padding: 15px; text-align: center; border-radius: 0 0 8px 8px; font-size: 12px; }}
.button {{ display: inline-block; padding: 12px 24px; background: #c9a84c; color: white; text-decoration: none; border-radius: 4px; margin: 10px 0; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>Fixed Deposit Confirmation</h1>
<p>Thank you for choosing Bank POC</p>
</div>
<div class="content">
<p>Dear {customer_name},</p>
<p>Your Fixed Deposit has been successfully created! Please find your certificate attached to this email.</p>

<div class="fd-details">
<h3>FD Details</h3>
<table>
<tr><td>FD Number:</td><td>{fd_instance.fd_id}</td></tr>
<tr><td>Bank:</td><td>{fd_instance.bank_name}</td></tr>
<tr><td>Deposit Amount:</td><td>&#8377;{float(fd_instance.amount):,}</td></tr>
<tr><td>Interest Rate:</td><td>{float(fd_instance.rate)}%</td></tr>
<tr><td>Tenure:</td><td>{fd_instance.tenure_months} months</td></tr>
<tr><td>Start Date:</td><td>{fd_instance.start_date.strftime('%B %d, %Y')}</td></tr>
<tr><td>Maturity Date:</td><td>{fd_instance.maturity_date.strftime('%B %d, %Y')}</td></tr>
<tr><td>Maturity Amount:</td><td>&#8377;{float(fd_instance.maturity_amount):,}</td></tr>
<tr><td>Interest Earned:</td><td>&#8377;{float(fd_instance.interest_earned):,}</td></tr>
</table>
</div>

<p>Your FD certificate is attached to this email. You can also download it from your account dashboard.</p>

<p style="text-align: center;">
<a href="{settings.SITE_URL or 'http://localhost:8000'}" class="button">View in Dashboard</a>
</p>

<p>Should you have any questions, please do not hesitate to contact us.</p>

<p>Best regards,<br>Bank POC Team</p>
</div>
<div class="footer">
<p>This is an automated message. Please do not reply directly to this email.</p>
<p>&copy; {datetime.now().year} Bank POC. All rights reserved.</p>
</div>
</div>
</body>
</html>
"""

        # Create email message
        email = EmailMultiAlternatives(
            subject=subject,
            body=f"Dear {customer_name}, Your Fixed Deposit {fd_instance.fd_id} has been created successfully. See attached certificate.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[customer_email]
        )

        # Attach HTML alternative
        email.attach_alternative(html_content, "text/html")

        # Attach certificate PDF
        with open(full_certificate_path, 'rb') as f:
            email.attach(
                f"FD_Certificate_{fd_instance.fd_id}.pdf",
                f.read(),
                'application/pdf'
            )

        # Send email
        email.send()

        logger.info(f"FD confirmation email sent to {customer_email}")
        return True

    except Exception as e:
        logger.error(f"Error sending FD confirmation email: {e}")
        traceback.print_exc()
        return False