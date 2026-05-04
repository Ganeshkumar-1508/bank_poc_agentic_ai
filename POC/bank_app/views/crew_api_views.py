"""
Simplified CrewAI API endpoints.

This module provides a single generic endpoint for executing all CrewAI crews.
Replaces the previous 11 separate endpoints with one unified interface.

Usage:
POST /api/run-crew/
Body: {
  "crew_type": "analysis",
  "query": "What are the best FD rates?",
  "region": "India" (optional),
  "additional_params": {} (optional)
}
"""

import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from .base import get_user_region_from_session

logger = logging.getLogger(__name__)


def _transform_india_to_us_format(india_data: dict) -> dict:
    """
    Transform India credit risk form data to US loan creation format.
    
    India form fields (CIBIL-based):
    - applicant_income, coapplicant_income
    - credit_score (CIBIL 300-900)
    - dti_ratio
    - loan_amount, loan_term
    - collateral_value, savings
    - employment_status, education_level
    - property_area, existing_loans
    - loan_purpose, email
    
    US format expected (FICO-based):
    - fico_score, annual_inc, dti, loan_amnt
    - delinq_2yrs, inq_last_6mths, pub_rec, revol_util
    - emp_length, home_ownership, purpose
    
    Args:
        india_data: Dictionary containing India-formatted loan application data
        
    Returns:
        Dictionary containing US-formatted borrower data
    """
    # Detect if this is India format by checking for India-specific fields
    india_fields = ['credit_score', 'applicant_income', 'dti_ratio']
    is_india_format = any(field in india_data for field in india_fields)
    
    if not is_india_format:
        # Already in US format or unknown format, return as-is
        return india_data
    
    logger.info(f"Detected India format data, transforming to US format. Input: {india_data}")
    
    # Map India fields to US equivalents
    us_data = {}
    
    # Income mapping
    applicant_income = float(india_data.get('applicant_income', 0) or 0)
    coapplicant_income = float(india_data.get('coapplicant_income', 0) or 0)
    us_data['annual_inc'] = applicant_income + coapplicant_income
    
    # Credit score mapping: CIBIL (300-900) to FICO (300-850)
    # CIBIL range: 300-900, FICO range: 300-850
    # Simple linear scaling: fico = 300 + (cibil - 300) * (850 - 300) / (900 - 300)
    credit_score = int(india_data.get('credit_score', 0) or 0)
    if credit_score >= 300 and credit_score <= 900:
        us_data['fico_score'] = 300 + int((credit_score - 300) * 550 / 600)
    else:
        us_data['fico_score'] = 300  # Default to minimum if out of range
    
    # DTI ratio mapping
    dti_ratio = float(india_data.get('dti_ratio', 0) or 0)
    us_data['dti'] = dti_ratio
    
    # Loan amount mapping
    loan_amount = float(india_data.get('loan_amount', 0) or 0)
    us_data['loan_amnt'] = loan_amount
    
    # Loan term (keep as is, may need conversion to months if needed)
    loan_term = int(india_data.get('loan_term', 0) or 0)
    us_data['loan_term'] = loan_term
    
    # Set default values for US-specific fields not in India form
    us_data['delinq_2yrs'] = 0  # No delinquencies by default
    us_data['inq_last_6mths'] = 0  # No recent inquiries by default
    us_data['pub_rec'] = 0  # No public records by default
    us_data['revol_util'] = 30  # Default 30% credit utilization
    
    # Map employment status to emp_length
    employment_status = india_data.get('employment_status', '').lower()
    if '10+' in employment_status or 'decade' in employment_status:
        us_data['emp_length'] = '10+ years'
    elif '5' in employment_status or 'five' in employment_status:
        us_data['emp_length'] = '5-10 years'
    elif '3' in employment_status or 'three' in employment_status:
        us_data['emp_length'] = '3-5 years'
    elif '1' in employment_status or 'one' in employment_status:
        us_data['emp_length'] = '1-3 years'
    else:
        us_data['emp_length'] = '< 1 year'
    
    # Map home ownership (default to RENT since India form doesn't specify)
    us_data['home_ownership'] = 'RENT'
    
    # Map loan purpose
    loan_purpose = india_data.get('loan_purpose', '').lower()
    purpose_mapping = {
        'business': 'business',
        'home': 'home_improvement',
        'car': 'car',
        'education': 'education',
        'wedding': 'wedding',
        'medical': 'medical',
        'vacation': 'vacation',
        'debt_consolidation': 'debt_consolidation',
        'other': 'other'
    }
    us_data['purpose'] = purpose_mapping.get(loan_purpose, 'other')
    
    # Include additional India fields that may be useful
    us_data['collateral_value'] = float(india_data.get('collateral_value', 0) or 0)
    us_data['savings'] = float(india_data.get('savings', 0) or 0)
    us_data['education_level'] = india_data.get('education_level', '')
    us_data['property_area'] = india_data.get('property_area', '')
    us_data['existing_loans'] = int(india_data.get('existing_loans', 0) or 0)
    us_data['email'] = india_data.get('email', '')
    
    # Convert to JSON string format expected by create_loan_creation_tasks
    borrower_context = json.dumps(us_data)
    
    logger.info(f"Transformed India data to US format: {borrower_context}")
    
    return borrower_context


# =============================================================================
# CREWAI IMPORTS - With graceful fallback
# =============================================================================

CREWAI_AVAILABLE = False
try:
    from crewai import Crew, Process
    CREWAI_AVAILABLE = True
    logger.info("CrewAI imported successfully in crew_api_views")
except ImportError:
    logger.warning("CrewAI not available in crew_api_views. Install with: pip install crewai crewai-tools")
    Crew = None
    Process = None

# Import all agent creators - with graceful fallback
create_router_agents = None
create_analysis_agents = None
create_research_agents = None
create_database_agents = None
create_visualization_agents = None
create_credit_risk_agents = None
create_loan_creation_agents = None
create_mortgage_agents = None
create_aml_agents = None
create_td_fd_agents = None
create_fd_template_agents = None

create_routing_task = None
create_analysis_tasks = None
create_research_tasks = None
create_database_tasks = None
create_visualization_task = None
create_credit_risk_tasks = None
create_loan_creation_tasks = None
create_mortgage_analytics_tasks = None
create_aml_execution_tasks = None
create_td_fd_tasks = None
create_fd_template_tasks = None

if CREWAI_AVAILABLE:
    try:
        from agents import (
            create_router_agents,
            create_analysis_agents,
            create_research_agents,
            create_database_agents,
            create_visualization_agents,
            create_credit_risk_agents,
            create_loan_creation_agents,
            create_mortgage_agents,
            create_aml_agents,
            create_td_fd_agents,
            create_fd_template_agents,
        )

        # Import all task creators
        from tasks import (
            create_routing_task,
            create_analysis_tasks,
            create_research_tasks,
            create_database_tasks,
            create_visualization_task,
            create_credit_risk_tasks,
            create_loan_creation_tasks,
            create_mortgage_analytics_tasks,
            create_aml_execution_tasks,
            create_td_fd_tasks,
            create_fd_template_tasks,
        )
        logger.info("CrewAI crew functions imported successfully in crew_api_views")
    except ImportError as e:
        logger.warning(f"Could not import crew functions in crew_api_views: {e}")

# Mapping of crew_type to (agent_creator, task_creator)
# Each entry: (agent_creator_func, task_creator_func)
# task_creator_func signature: (agents, query, region) -> list of tasks
CREW_FUNCTION_MAP = {
    "router": (
        create_router_agents,
        lambda agents, query, region: [create_routing_task(agents, query, region or "India")],
    ),
    "analysis": (
        create_analysis_agents,
        lambda agents, query, region: create_analysis_tasks(agents, query, region or "India"),
    ),
    "research": (
        create_research_agents,
        lambda agents, query, region: create_research_tasks(agents, query, region or "India"),
    ),
    "database": (
        create_database_agents,
        lambda agents, query, region: create_database_tasks(agents, query),
    ),
    "visualization": (
        create_visualization_agents,
        lambda agents, query, region: [create_visualization_task(agents, query, query)],
    ),
    "credit_risk": (
        create_credit_risk_agents,
        lambda agents, query, region: create_credit_risk_tasks(
            agents, json.dumps(query) if isinstance(query, dict) else query, region
        ),
    ),
    "loan_creation": (
        create_loan_creation_agents,
        lambda agents, query, region: create_loan_creation_tasks(agents, query),
    ),
    "mortgage_analytics": (
        create_mortgage_agents,
        lambda agents, query, region: create_mortgage_analytics_tasks(
            agents, json.dumps(query) if isinstance(query, dict) else query
        ),
    ),
    "aml": (
        create_aml_agents,
        lambda agents, query, region: create_aml_execution_tasks(
            agents, json.dumps(query) if isinstance(query, dict) else query
        ),
    ),
    "fd_advisor": (
        create_td_fd_agents,
        lambda agents, query, region: create_td_fd_tasks(
            agents, json.dumps(query) if isinstance(query, dict) else query
        ),
    ),
    "fd_template": (
        create_fd_template_agents,
        lambda agents, query, region: create_fd_template_tasks(agents, {}),
    ),
}


@csrf_exempt
@require_POST
def run_crew(request):
    """
    Generic CrewAI execution endpoint.

    Replaces all 11 previous crew endpoints with a single unified interface.

    POST /api/run-crew/
    Body: {
        "crew_type": "analysis" | "router" | "research" | "database" |
                     "visualization" | "credit_risk" | "loan_creation" |
                     "mortgage_analytics" | "aml" | "fd_advisor" | "fd_template",
        "query": "The user's query string",
        "region": "India" (optional, default: "India"),
        "additional_params": {} (optional, for future extensibility)
    }

    Response:
    {
        "result": "The raw output from crew.kickoff()",
        "crew_type": "the crew type that was executed"
    }
    """
    if not CREWAI_AVAILABLE:
        return JsonResponse(
            {"error": "CrewAI not available. Please install with: pip install crewai crewai-tools"},
            status=503,
        )
    
    try:
        # Safely read request body - handle edge cases where body may have been consumed
        try:
            raw_data = request.body
        except AttributeError as e:
            # Fallback for edge cases where _read_started attribute is missing
            logger.error(f"Request body access error: {e}")
            # Try to read from stream directly
            if hasattr(request, 'stream') and request.stream:
                raw_data = request.stream.read()
            else:
                return JsonResponse(
                    {"error": "Unable to read request body. Please ensure the request is properly formatted."},
                    status=400
                )
        
        data = json.loads(raw_data)
        crew_type = data.get("crew_type", "").lower()
        query = data.get("query", "")
        # Get region from request body first, then fallback to session
        region = data.get("region")
        if not region:
            region_data = get_user_region_from_session(request)
            region = region_data.get("country_name", "India")
    
        # Validate crew_type
        if crew_type not in CREW_FUNCTION_MAP:
            return JsonResponse(
                {
                    "error": f"Unknown crew_type: {crew_type}. Valid types: {list(CREW_FUNCTION_MAP.keys())}"
                },
                status=400,
            )
    
        # Validate query - accept both string and object/dict formats
        if not query:
            return JsonResponse({"error": "query is required"}, status=400)
        if isinstance(query, str) and not query.strip():
            return JsonResponse({"error": "query is required"}, status=400)
    
        # Check if agent/task creators are available
        agent_creator, task_creator = CREW_FUNCTION_MAP[crew_type]
        if not agent_creator or not task_creator:
            return JsonResponse(
                {"error": f"CrewAI functions not available for {crew_type}"},
                status=503,
            )
    
        # Prepare query preview for logging
        if isinstance(query, str):
            query_preview = query[:50]
        elif isinstance(query, dict):
            query_preview = str(query)[:50]
        else:
            query_preview = str(query)[:50]
        logger.info(f"Executing crew: {crew_type}, query: {query_preview}...")
    
        # Create agents
        try:
            agents = agent_creator(region=region) if region else agent_creator()
        except Exception as e:
            logger.error(f"Failed to create agents for {crew_type}: {e}")
            return JsonResponse({"error": f"Agent creation failed: {str(e)}"}, status=500)

        # Create tasks
        try:
            tasks = task_creator(agents, query, region)
        except Exception as e:
            logger.error(f"Failed to create tasks for {crew_type}: {e}")
            return JsonResponse({"error": f"Task creation failed: {str(e)}"}, status=500)

        # Ensure tasks is a list
        if not isinstance(tasks, list):
            tasks = [tasks]

        if not tasks:
            return JsonResponse({"error": "No tasks created for this crew"}, status=500)

        # Prepare agents list
        if isinstance(agents, dict):
            agents_list = list(agents.values())
        else:
            agents_list = agents

        if not agents_list:
            return JsonResponse({"error": "No agents created for this crew"}, status=500)

        # Create and run crew
        crew = Crew(
            agents=agents_list,
            tasks=tasks,
            process=Process.sequential,
            verbose=False,
            cache=False,
        )

        output = crew.kickoff()

        # Extract result
        result = output.raw if hasattr(output, "raw") else str(output)

        logger.info(f"Crew {crew_type} executed successfully")

        return JsonResponse({"result": result, "crew_type": crew_type})

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request: {e}")
        return JsonResponse({"error": "Invalid JSON in request body"}, status=400)
    except Exception as e:
        logger.error(f"Crew execution error: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


# =============================================================================
# LEGACY ENDPOINTS - Redirect to new generic endpoint
# These are kept for backward compatibility during migration
# =============================================================================


def _legacy_endpoint_wrapper(crew_type: str, extract_params=None):
    """
    Create a legacy endpoint wrapper that redirects to run_crew.

    Args:
        crew_type: The crew type to execute
        extract_params: Optional function to extract params from request
        Signature: (request) -> (query, region, additional)
    """

    @csrf_exempt
    @require_POST
    def legacy_endpoint(request):
        try:
            # Read request body safely
            try:
                raw_data = request.body
            except AttributeError:
                if hasattr(request, 'stream') and request.stream:
                    raw_data = request.stream.read()
                else:
                    return JsonResponse(
                        {"error": "Unable to read request body."},
                        status=400
                    )

            data = json.loads(raw_data)

            # Special handling for AML crew - it expects client data, not a query string
            if crew_type == "aml":
                # Extract client data fields and convert to JSON string
                client_data = {
                    "client_name": data.get("client_name", ""),
                    "client_id": data.get("client_id", ""),
                    "email": data.get("email", ""),
                    "transaction_amount": data.get("transaction_amount", ""),
                    "transaction_type": data.get("transaction_type", "account_opening"),
                    "country_of_origin": data.get("country_of_origin", ""),
                    "date_of_birth": data.get("date_of_birth", ""),
                    "address": data.get("address", ""),
                    "occupation": data.get("occupation", ""),
                    "mobile_number": data.get("mobile_number", data.get("phone", "")),
                    "initial_amount": data.get("initial_amount", ""),
                }
                # Remove empty fields
                client_data = {k: v for k, v in client_data.items() if v}
                query = json.dumps(client_data)
                region = data.get("region", "India")
            # Special handling for loan_creation crew - transform India data to US format
            elif crew_type == "loan_creation":
                # Check if data is in India format and transform if needed
                query = _transform_india_to_us_format(data)
                region = data.get("region", "India")
            else:
                # Default extraction
                if extract_params:
                    query, region, _ = extract_params(data)
                else:
                    query = data.get("query", "")
                    region = data.get("region", "India")

            # Build forward data
            forward_data = {
                "crew_type": crew_type,
                "query": query,
                "region": region,
            }

            # Call run_crew directly with the forward data as a dict
            # We need to simulate a request that run_crew can work with
            # Instead of creating a new HttpRequest, we'll call the logic directly
            return _execute_crew(forward_data)

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in legacy endpoint: {e}")
            return JsonResponse({"error": "Invalid JSON in request body"}, status=400)
        except Exception as e:
            logger.error(f"Legacy endpoint error: {e}", exc_info=True)
            return JsonResponse({"error": str(e)}, status=500)

    return legacy_endpoint


def _execute_crew(forward_data):
    """
    Execute crew directly without going through run_crew request handling.

    Args:
        forward_data: dict with crew_type, query, region

    Returns:
        JsonResponse with result or error
    """
    if not CREWAI_AVAILABLE:
        return JsonResponse(
            {"error": "CrewAI not available. Please install with: pip install crewai crewai-tools"},
            status=503,
        )

    crew_type = forward_data.get("crew_type", "").lower()
    query = forward_data.get("query", "")
    region = forward_data.get("region")
    if not region:
        region = "India"

    # Validate crew_type
    if crew_type not in CREW_FUNCTION_MAP:
        return JsonResponse(
            {
                "error": f"Unknown crew_type: {crew_type}. Valid types: {list(CREW_FUNCTION_MAP.keys())}"
            },
            status=400,
        )

    # Validate query
    if not query:
        return JsonResponse({"error": "query is required"}, status=400)
    if isinstance(query, str) and not query.strip():
        return JsonResponse({"error": "query is required"}, status=400)

    # Check if agent/task creators are available
    agent_creator, task_creator = CREW_FUNCTION_MAP[crew_type]
    if not agent_creator or not task_creator:
        return JsonResponse(
            {"error": f"CrewAI functions not available for {crew_type}"},
            status=503,
        )

    # Prepare query preview for logging
    if isinstance(query, str):
        query_preview = query[:50]
    elif isinstance(query, dict):
        query_preview = str(query)[:50]
    else:
        query_preview = str(query)[:50]
    logger.info(f"Executing crew: {crew_type}, query: {query_preview}...")

    # Create agents
    try:
        # Only pass region to agents that accept it
        # Agents accepting region: analysis, research, credit_risk
        # Agents NOT accepting region: router, database, visualization, loan_creation,
        #                              mortgage_analytics, aml, fd_advisor, fd_template
        if crew_type in ("analysis", "research", "credit_risk"):
            agents = agent_creator(region=region) if region else agent_creator()
        else:
            agents = agent_creator()
    except Exception as e:
        logger.error(f"Failed to create agents for {crew_type}: {e}")
        return JsonResponse({"error": f"Agent creation failed: {str(e)}"}, status=500)

    # Create tasks
    try:
        tasks = task_creator(agents, query, region)
    except Exception as e:
        logger.error(f"Failed to create tasks for {crew_type}: {e}")
        return JsonResponse({"error": f"Task creation failed: {str(e)}"}, status=500)

    # Ensure tasks is a list
    if not isinstance(tasks, list):
        tasks = [tasks]

    if not tasks:
        return JsonResponse({"error": "No tasks created for this crew"}, status=500)

    # Prepare agents list
    if isinstance(agents, dict):
        agents_list = list(agents.values())
    else:
        agents_list = agents

    if not agents_list:
        return JsonResponse({"error": "No agents created for this crew"}, status=500)

    # Create and run crew
    crew = Crew(
        agents=agents_list,
        tasks=tasks,
        process=Process.sequential,
        verbose=False,
        cache=False,
    )

    output = crew.kickoff()
    
    # Extract result
    result = output.raw if hasattr(output, "raw") else str(output)
    
    logger.info(f"Crew {crew_type} executed successfully")
    
    # Special handling for AML crew to extract decision and pdf_path
    if crew_type == "aml":
        import re as _re
    
        pdf_path = None
        decision = None
    
        # Extract PDF path from task outputs or raw output
        tasks_output_raw = []
        if hasattr(output, "tasks_output"):
            for task_out in output.tasks_output:
                task_raw = task_out.raw if hasattr(task_out, "raw") else str(task_out)
                tasks_output_raw.append(task_raw)
                path_match = _re.search(
                    r"(outputs/sessions/\S+\.pdf|outputs/pdfs/\S+\.pdf|/\S+\.pdf)", task_raw
                )
                if path_match and not pdf_path:
                    pdf_path = path_match.group(1)
        
        # Also try to extract from the final raw output
        if not pdf_path:
            path_match = _re.search(
                r"(outputs/sessions/\S+\.pdf|outputs/pdfs/\S+\.pdf|/\S+\.pdf)", result
            )
            if path_match:
                pdf_path = path_match.group(1)
        
        # Detect PASS/FAIL decision
        upper_output = result.upper()
        if "DECISION: PASS" in upper_output or "APPLICATION APPROVED" in upper_output:
            decision = "PASS"
        elif (
            "DECISION: FAIL" in upper_output
            or "APPLICATION REJECTED" in upper_output
            or "TRANSACTION BLOCKED" in upper_output
        ):
            decision = "FAIL"
        
        return JsonResponse({
            "result": result,
            "crew_type": crew_type,
            "pdf_path": pdf_path,
            "decision": decision,
            "tasks_output": tasks_output_raw,
        })
    
    return JsonResponse({"result": result, "crew_type": crew_type})


# Legacy endpoints for backward compatibility - all 11 crew API endpoints
fd_advisor_crew_api = _legacy_endpoint_wrapper("fd_advisor")
credit_risk_crew_api = _legacy_endpoint_wrapper("credit_risk")
aml_crew_api = _legacy_endpoint_wrapper("aml")
financial_news_crew_api = _legacy_endpoint_wrapper("research")
router_crew_api = _legacy_endpoint_wrapper("router")
loan_creation_crew_api = _legacy_endpoint_wrapper("loan_creation")
mortgage_analytics_crew_api = _legacy_endpoint_wrapper("mortgage_analytics")
fd_template_crew_api = _legacy_endpoint_wrapper("fd_template")
visualization_crew_api = _legacy_endpoint_wrapper("visualization")
analysis_crew_api = _legacy_endpoint_wrapper("analysis")
database_crew_api = _legacy_endpoint_wrapper("database")
