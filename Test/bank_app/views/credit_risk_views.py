"""
Credit Risk Assessment Views.
Contains endpoints for credit risk evaluation using ML models and CrewAI.
"""

import os
import json
import logging
import traceback
import numpy as np
import joblib
import markdown

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .base import (
    logger,
    INDIAN_MODEL_PATH,
    INDIAN_SCALER_PATH,
    US_MODEL_PATH,
)

logger = logging.getLogger(__name__)


# =============================================================================
# INDIAN CREDIT RISK API
# =============================================================================

@csrf_exempt
def credit_risk_indian_api(request):
    """
    API endpoint for Indian credit risk assessment.

    POST /api/credit-risk/indian/
    Body: {
        "loan_amount": 500000,
        "applicant_income": 600000,
        "dti_ratio": 35,
        "credit_score": 720,
        "collateral_value": 100000,
        "loan_term": 36,
        "savings": 50000
    }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)

        if not os.path.exists(INDIAN_MODEL_PATH):
            return JsonResponse({'error': 'Indian model not found'}, status=500)

        model = joblib.load(INDIAN_MODEL_PATH)
        scaler = joblib.load(INDIAN_SCALER_PATH) if os.path.exists(INDIAN_SCALER_PATH) else None

        # Prepare features
        loan_amount = float(data.get('loan_amount', 0))
        annual_income = float(data.get('applicant_income', data.get('annual_income', 0)))
        dti_ratio = float(data.get('dti_ratio', 0))
        credit_score = float(data.get('credit_score', 0))
        collateral_value = float(data.get('collateral_value', 0))
        loan_term = float(data.get('loan_term', 0))
        savings = float(data.get('savings', 0))

        feature_vector = np.array([[loan_amount, annual_income, dti_ratio, credit_score,
                                    collateral_value, loan_term, savings]])

        if scaler:
            feature_vector = scaler.transform(feature_vector)

        prediction = model.predict(feature_vector)[0]
        prediction_proba = model.predict_proba(feature_vector)[0]

        approval_prob = float(prediction_proba[1] if len(prediction_proba) > 1 else 0.5)
        verdict = "APPROVED" if prediction == 1 else "REJECTED"

        return JsonResponse({
            'approval_probability': round(approval_prob * 100, 2),
            'verdict': verdict,
            'key_factors': ['Credit Score', 'DTI Ratio', 'Loan Amount'],
            'improvement_tips': [
                'Increase credit score by paying bills on time',
                'Reduce debt-to-income ratio',
                'Provide additional collateral'
            ]
        })

    except Exception as e:
        logger.error(f"Indian credit risk error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# US CREDIT RISK API
# =============================================================================

@csrf_exempt
def credit_risk_us_api(request):
    """
    US Credit Risk API endpoint - Uses XGBoost model for US credit assessment.

    POST /api/credit-risk/us/
    Body: JSON with applicant financial data
    Returns: approval_probability, verdict, key_factors
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)

        if not os.path.exists(US_MODEL_PATH):
            return JsonResponse({'error': 'US model not found'}, status=500)

        model = joblib.load(US_MODEL_PATH)

        # Prepare features for US model
        annual_income = float(data.get('annual_income', data.get('applicant_income', 0)))
        loan_amount = float(data.get('loan_amount', 0))
        credit_score = float(data.get('credit_score', 0))
        dti_ratio = float(data.get('dti_ratio', 0))
        employment_years = float(data.get('employment_years', 0))
        num_credit_lines = float(data.get('num_credit_lines', 3))
        num_delinquencies = float(data.get('num_delinquencies', 0))

        feature_vector = np.array([[
            annual_income,
            loan_amount,
            credit_score,
            dti_ratio,
            employment_years,
            num_credit_lines,
            num_delinquencies
        ]])

        prediction = model.predict(feature_vector)[0]
        prediction_proba = model.predict_proba(feature_vector)[0]

        approval_prob = float(prediction_proba[1] if len(prediction_proba) > 1 else 0.5)
        verdict = "APPROVED" if prediction == 1 else "REJECTED"

        return JsonResponse({
            'approval_probability': round(approval_prob * 100, 2),
            'verdict': verdict,
            'key_factors': ['Credit Score', 'DTI Ratio', 'Employment History'],
            'improvement_tips': [
                'Maintain credit utilization below 30%',
                'Pay all bills on time',
                'Avoid opening multiple new accounts'
            ]
        })

    except Exception as e:
        logger.error(f"US credit risk error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# GENERAL CREDIT RISK API (Routes based on detected region)
# =============================================================================

def get_user_region_from_request(request):
    """
    Get user region from request session or headers.
    Returns the country code (e.g., 'IN', 'US') or defaults to 'IN'.
    """
    # Check session first
    user_region = request.session.get('user_region', {})
    if user_region and user_region.get('country_code'):
        return user_region['country_code'].upper()

    # Check headers for region info (set by middleware)
    country_code = request.headers.get('X-Country-Code')
    if country_code:
        return country_code.upper()

    # Default to India
    return 'IN'


@csrf_exempt
def credit_risk_api(request):
    """
    General credit risk API endpoint.
    Routes to Indian or US model based on detected user region.

    POST /api/credit-risk/
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        # Detect user region from session
        user_region = get_user_region_from_request(request)
        logger.info(f"Credit Risk API: Detected region: {user_region}")

        # Route to appropriate model based on region
        if user_region == 'US':
            return credit_risk_us_api(request)
        else:
            # Default to Indian model for India and all other regions
            return credit_risk_indian_api(request)
    except Exception as e:
        logger.error(f"Credit risk API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# CREDIT RISK CREW API endpoint
# =============================================================================

@csrf_exempt
def credit_risk_crew_api(request):
    """
    Credit Risk Crew API endpoint - Uses CrewAI for comprehensive credit risk assessment.
    Routes to region-specific models based on user's detected region.

    POST /api/credit-risk-crew/
    Body: {
        "query": {borrower_data_object}, # NOT JSON-encoded string
        "region": "India" # Optional - will be detected from session if not provided
    }

    Returns: Structured results from CrewAI credit risk crew
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        logger.info("=== credit_risk_crew_api called ===")
        logger.info(f"Request body: {request.body.decode('utf-8')[:500]}")

        data = json.loads(request.body)
        logger.info(f"Parsed request data: {data}")

        # Validate required fields
        query = data.get('query', {})
        logger.info(f"Query type: {type(query)}, value: {query}")

        # Use provided region or detect from session
        region = data.get('region')
        logger.info(f"Region from request: {region}")

        if not region:
            region = get_user_region_from_request(request)
            logger.info(f"Region detected from session: {region}")

        # Normalize region to country code
        region_code = region.upper() if region else 'IN'
        logger.info(f"Normalized region_code: {region_code}")

        # Detect region type
        us_regions = ('US', 'UNITED STATES', 'USA')
        india_regions = ('IN', 'INDIA', 'BHARAT')

        is_us_region = region_code in us_regions
        is_india_region = region_code in india_regions

        logger.info(f"is_us_region: {is_us_region}, is_india_region: {is_india_region}")

        # Route to appropriate model based on region
        if not is_us_region and not is_india_region:
            logger.warning(f"Region not supported: {region_code}")
            return JsonResponse({
                'error': 'Region not supported',
                'detail': f'Credit Risk Assessment is currently only available for US and India regions. Detected: {region}',
                'region': region_code,
                'supported_regions': ['US', 'IN']
            }, status=400)

        # Handle both dict and string query inputs
        if isinstance(query, str):
            logger.info("Query is a string, parsing JSON...")
            try:
                borrower_data = json.loads(query)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
                return JsonResponse({'error': 'Invalid JSON in query field'}, status=400)
        else:
            logger.info("Query is already a dict/object")
            borrower_data = query

        logger.info(f"Final borrower_data: {borrower_data}")

        if not borrower_data:
            logger.warning("Borrower data is empty")
            return JsonResponse({'error': 'Borrower data is required'}, status=400)

        # Log the request
        logger.info(f"Credit Risk Crew: Starting analysis for region={region_code}")
        logger.info(f"Borrower data keys: {list(borrower_data.keys()) if isinstance(borrower_data, dict) else 'N/A'}")

        # Import and run the credit risk crew with region parameter
        import sys
        from pathlib import Path

        # Get the absolute path to the Test/ directory (where crews.py is located)
        # __file__ = Test/bank_app/views/credit_risk_views.py
        # parent.parent.parent = Test/
        test_dir = Path(__file__).resolve().parent.parent.parent
        test_dir_str = str(test_dir)

        logger.info(f"Test directory: {test_dir_str}")

        # Add Test/ to sys.path if not already present
        if test_dir_str not in sys.path:
            sys.path.insert(0, test_dir_str)
            logger.info(f"Added {test_dir_str} to sys.path")

        # Verify the crews module can be found
        crews_path = test_dir / 'crews.py'
        if not crews_path.exists():
            error_msg = f"crews.py not found at {crews_path}. sys.path: {sys.path[:5]}"
            logger.error(error_msg)
            return JsonResponse({'error': error_msg}, status=500)

        logger.info(f"crews.py found at {crews_path}")

        try:
            from crews import run_credit_risk_crew
            logger.info("Successfully imported run_credit_risk_crew from crews module")
        except ImportError as import_err:
            error_msg = f"Failed to import run_credit_risk_crew: {import_err}"
            logger.error(error_msg)
            logger.error(f"sys.path: {sys.path[:5]}")
            return JsonResponse({
                'error': error_msg,
                'detail': 'CrewAI module import failed. Check server logs for details.'
            }, status=500)

        # Convert borrower_data to JSON string for the crew function
        borrower_json = json.dumps(borrower_data) if isinstance(borrower_data, dict) else str(borrower_data)

        logger.info(f"Calling run_credit_risk_crew with borrower_json (length={len(borrower_json)}) and region={region_code}")
        logger.info(f"Borrower data preview: {borrower_data}")

        try:
            result = run_credit_risk_crew(borrower_json, region=region_code)
        except Exception as crew_error:
            logger.error(f"CrewAI execution failed: {crew_error}")
            return JsonResponse({
                'error': 'CrewAI execution failed',
                'detail': str(crew_error),
                'borrower_data': borrower_data,
                'region': region_code
            }, status=500)

        logger.info("Credit Risk CrewAI analysis completed successfully")

        # Extract result - handle both CrewOutput objects and string results
        if hasattr(result, 'raw'):
            analysis_result = result.raw
        elif hasattr(result, 'dict'):
            analysis_result = result.dict()
        else:
            analysis_result = str(result)
        
        logger.info(f"Analysis result type: {type(analysis_result)}")
        
        # Try to parse as JSON first (new structured output format)
        structured_data = None
        is_json = False
        summary_html = ''
        
        try:
            # Try to parse as JSON - handles both string JSON and dict results
            if isinstance(analysis_result, str):
                structured_data = json.loads(analysis_result)
            elif isinstance(analysis_result, dict):
                structured_data = analysis_result
            else:
                structured_data = None
            
            if structured_data:
                is_json = True
                logger.info(f"Successfully parsed JSON output with keys: {list(structured_data.keys())}")
                
                # Extract structured sections
                ml_prediction = structured_data.get('ml_prediction', {})
                policy_excerpts = structured_data.get('policy_excerpts', [])
                compliance_status = structured_data.get('compliance_status', {})
                
                logger.info(f"ML prediction: {ml_prediction}")
                logger.info(f"Policy excerpts count: {len(policy_excerpts) if isinstance(policy_excerpts, list) else 'N/A'}")
                logger.info(f"Compliance status: {compliance_status}")
                
                # For backward compatibility, also render the full JSON as HTML if needed
                summary_html = json.dumps(structured_data, indent=2)
        except (json.JSONDecodeError, TypeError) as json_err:
            logger.info(f"Result is not JSON (fallback to markdown): {json_err}")
            is_json = False
            structured_data = None
        
        # If not JSON or no structured data, render markdown (backward compatibility)
        if not is_json and analysis_result:
            analysis_result_str = str(analysis_result)
            logger.info(f"Rendering markdown (length={len(analysis_result_str)})")
            try:
                summary_html = markdown.markdown(
                    analysis_result_str,
                    extensions=['fenced_code', 'tables', 'nl2br', 'extra', 'codehilite']
                )
                logger.info(f"Markdown rendered successfully (HTML length={len(summary_html)})")
                logger.info(f"HTML preview: {summary_html[:200]}...")
            except Exception as md_error:
                logger.error(f"Markdown rendering failed: {md_error}")
                summary_html = analysis_result_str # Fallback to raw text
        
        # Build response context
        response_data = {
            'success': True,
            'result': analysis_result,
            'summary_html': summary_html,
            'region': region_code,
            'is_us_region': is_us_region,
            'is_india_region': is_india_region,
            'borrower_data': borrower_data,
            'is_json': is_json,
        }
        
        # Add structured data sections if JSON was parsed
        if is_json and structured_data:
            response_data['ml_prediction'] = structured_data.get('ml_prediction', {})
            response_data['policy_excerpts'] = structured_data.get('policy_excerpts', [])
            response_data['compliance_status'] = structured_data.get('compliance_status', {})
        
        return JsonResponse(response_data)

    except json.JSONDecodeError as json_err:
        error_msg = f"Invalid JSON in request body: {json_err}"
        logger.error(error_msg)
        return JsonResponse({'error': error_msg}, status=400)
    except Exception as e:
        error_msg = f"Unexpected error in credit_risk_crew_api: {e}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        return JsonResponse({
            'error': str(e),
            'detail': 'An unexpected error occurred. Check server logs for details.'
        }, status=500)